import io
import os
import uuid
from typing import List, Optional
import zipfile

from werkzeug.datastructures import FileStorage

from src.models.image import Image
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.repositories.db.image_repo import ImageRepo
from src.repositories.db.training_run_repo import TrainingRunRepo
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.services.aws.sqs import SqsClient
from src.utils.config import AppConfig

class ImageService:
    def __init__(self):
        self.image_repo = ImageRepo()
        self.model_project_repo = ModelProjectRepo()
        self.training_run_repo = TrainingRunRepo()
        self.generation_history_repo = GenerationHistoryRepo()
        self._temp_prefix = "temp/uploads"

    def _get_user_id(self) -> str:
        return self.image_repo.get_current_user_id()

    def _build_temp_upload_key(self, project_id: str, image_id: str, filename: str) -> str:
        user_id = self._get_user_id()
        project_id = str(project_id)
        safe_filename = filename.replace("/", "_")
        return f"{self._temp_prefix}/{user_id}/{project_id}/{image_id}_{safe_filename}"

    def create_presigned_uploads(self, project_id: str, files: List[dict], image_type: str = "training"):
        if not project_id:
            raise ValueError("Project ID is required")
        if not files:
            raise ValueError("No files provided")

        storage = self.image_repo.storage
        if not hasattr(storage, "generate_presigned_upload"):
            raise ValueError("Presigned uploads are not supported for this storage backend")

        uploads = []
        for file_data in files:
            filename = file_data.get("filename")
            if not filename:
                raise ValueError("Each file entry must include a filename")
            content_type = file_data.get("content_type") or "application/octet-stream"
            resize = file_data.get("resize", True)
            image_id = str(uuid.uuid4())
            temp_key = self._build_temp_upload_key(project_id, image_id, filename)
            presigned = storage.generate_presigned_upload(temp_key, content_type)
            uploads.append({
                "image_id": image_id,
                "filename": filename,
                "content_type": content_type,
                "resize": resize,
                "upload_url": presigned["url"],
                "method": presigned.get("method", "PUT"),
                "headers": presigned.get("headers", {}),
            })

        return uploads

    def dispatch_presigned_uploads(self, project_id: str, uploads: List[dict], image_type: str = "training"):
        if not project_id:
            raise ValueError("Project ID is required")
        if not uploads:
            raise ValueError("No uploads provided")

        results = []
        for upload in uploads:
            image_id = upload.get("image_id")
            filename = upload.get("filename")
            if not image_id or not filename:
                raise ValueError("Each upload must include image_id and filename")
            content_type = upload.get("content_type") or "application/octet-stream"
            resize = upload.get("resize", True)
            temp_key = self._build_temp_upload_key(project_id, image_id, filename)

            image = self._enqueue_normalization_job(
                project_id=project_id,
                file=None,
                filename=filename,
                image_type=image_type,
                resize=resize,
                image_id=image_id,
                temp_key=temp_key,
                content_type=content_type,
            )

            results.append({
                "id": image.id,
                "filename": image.filename,
                "content_type": image.content_type,
                "size_bytes": image.size_bytes,
                "image_type": image.image_type,
                "processing": image.processing,
                "created_at": image.created_at.isoformat() if image.created_at else None
            })

        return results

    def upload_image(
        self,
        project_id: str,
        file: FileStorage,
        filename: str,
        image_type: str = "training",
        resize: bool = True,
        image_id: Optional[str] = None,
    ) -> Image:
        """Upload an image for a project"""
        # Note: We don't validate project here because this service is used for both
        # regular projects and story projects, which are in different collections.
        # The controller should handle authentication/authorization.

        return self._enqueue_normalization_job(
            project_id=project_id,
            file=file,
            filename=filename,
            image_type=image_type,
            resize=resize,
            image_id=image_id,
        )

    def _enqueue_normalization_job(
        self,
        project_id: str,
        file: Optional[FileStorage],
        filename: str,
        image_type: str,
        resize: bool,
        image_id: Optional[str] = None,
        temp_key: Optional[str] = None,
        content_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> Image:
        queue_url = os.getenv("IMAGE_UPLOAD_QUEUE_URL")
        if not queue_url:
            raise ValueError("IMAGE_UPLOAD_QUEUE_URL must be set")

        image_id = image_id or str(uuid.uuid4())
        user_id = self._get_user_id()
        project_id = str(project_id)

        temp_key = temp_key or self._build_temp_upload_key(project_id, image_id, filename)
        destination_key = self.image_repo.build_s3_key(project_id, image_id, filename)

        if file is not None:
            file.stream.seek(0)
            file_bytes = file.stream.read()
            file_stream = io.BytesIO(file_bytes)
            file_stream.seek(0)
            temp_file = FileStorage(
                stream=file_stream,
                filename=filename,
                content_type=file.content_type,
            )
            temp_file.headers["Content-Length"] = str(len(file_bytes))
            self.image_repo.storage.upload_file(temp_file, temp_key)
            size_bytes = len(file_bytes)
            content_type = file.content_type
        else:
            size_bytes = size_bytes or 0
            content_type = content_type or "application/octet-stream"

        image = self.image_repo.create_image_record(
            project_id=project_id,
            image_id=image_id,
            filename=filename,
            s3_key=destination_key,
            content_type=content_type,
            size_bytes=size_bytes,
            image_type=image_type,
            processing=True,
        )

        if image_type == "training":
            self.training_run_repo.add_images_to_draft(project_id, [image_id])
        elif image_type == "reference":
            self.generation_history_repo.add_reference_images_to_draft(project_id, [image_id])

        sqs = SqsClient(region=AppConfig.AWS_REGION)
        sqs.send_message(
            queue_url=queue_url,
            message_body={
                "image_id": image_id,
                "resize": bool(resize),
            },
        )

        return image

    def download_image(self, image_id: str) -> Optional[bytes]:
        """Download an image by ID"""
        return self.image_repo.download_image(image_id)

    def delete_image(self, image_id: str):
        """Delete an image by ID"""
        image = self.image_repo.get_image(image_id)
        if image.image_type == "training":
            self.training_run_repo.remove_images_from_draft(image.project_id, [image_id])
        elif image.image_type == "reference":
            self.generation_history_repo.remove_reference_images_from_draft(
                image.project_id,
                [image_id],
            )
        self.image_repo.delete_image(image_id)

    def list_images(self, project_id: str, image_type: Optional[str] = None) -> List[Image]:
        """List all images for a project, optionally filtered by image type"""
        # Note: We don't validate project here because this service is used for both
        # regular projects and story projects, which are in different collections.
        # The controller should handle authentication/authorization.
        return self.image_repo.list_images(project_id, image_type)

    def list_draft_training_images(self, project_id: str) -> List[Image]:
        """List images attached to the current draft training run."""
        draft = self.training_run_repo.get_draft_by_project(project_id)
        if not draft or not draft.image_ids:
            return []
        return self.get_images_by_ids(draft.image_ids)

    def get_images_by_ids(self, image_ids: List[str]) -> List[Image]:
        """Fetch specific images for the current user by ID."""
        return self.image_repo.get_images_by_ids(image_ids)

    def create_zip(self, project_id: str):
        """Create a zip file of all training images for a project"""
        project = self.model_project_repo.get_project(project_id)
        # List only training images for the project
        images = self.list_images(project_id, image_type="training")
        # Create an in-memory zip file
        zip_buffer = io.BytesIO()
        # Create a zip file in memory
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            index = 0
            for image in images:
                # Download each file
                file_blob = self.download_image(image.id)
                # Rename the file so that the AI knows the subject
                file_extension = os.path.splitext(image.filename)[1]
                fileName = f"a_photo_of_{project.subject_name}({index}){file_extension}"
                # Add the image to the zip file
                zip_file.writestr(fileName, file_blob)
                index = index + 1
        # After adding all files, get the contents of the zip file
        zip_buffer.seek(0)  # Go to the beginning of the buffer before returning it
        zip_buffer.name = "training_images.zip"
        return zip_buffer

    def create_zip_from_images(self, image_ids: list):
        """Create a zip file from specific image IDs"""
        # Get the first image to determine the project
        if not image_ids:
            raise ValueError("At least one image ID is required")

        first_image = self.image_repo.get_image(image_ids[0])
        project = self.model_project_repo.get_project(first_image.project_id)

        # Create an in-memory zip file
        zip_buffer = io.BytesIO()
        # Create a zip file in memory
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            index = 0
            for image_id in image_ids:
                # Get image metadata
                image = self.image_repo.get_image(image_id)
                # Download the file
                file_blob = self.download_image(image_id)
                # Rename the file so that the AI knows the subject
                file_extension = os.path.splitext(image.filename)[1]
                fileName = f"a_photo_of_{project.subject_name}({index}){file_extension}"
                # Add the image to the zip file
                zip_file.writestr(fileName, file_blob)
                index = index + 1
        # After adding all files, get the contents of the zip file
        zip_buffer.seek(0)  # Go to the beginning of the buffer before returning it
        zip_buffer.name = "training_images.zip"
        return zip_buffer
    
