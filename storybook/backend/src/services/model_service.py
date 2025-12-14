# https://replicate.com/blog/fine-tune-flux
from typing import List
import replicate
from flask import request
import requests
from io import BytesIO
from werkzeug.datastructures import FileStorage

from src.models.image import Image
from src.services.image_service import ImageService

class ModelService:

    def __init__(self):
        self.image_service = ImageService()

    def __get_model_name(self, project_id):
        user_id = request.cognito_claims['sub']
        model_name = f"flux_{user_id}_{project_id}"
        return model_name

    def exists(self, project_id: str) -> bool:
        model_name = self.__get_model_name(project_id)
        try:
            # Try to get the model by name
            replicate.models.get(f"ansavva/{model_name}")
            return True
        except:
            return False

    def train(self, project_id: str) -> str:
        model_name = self.__get_model_name(project_id)
        try:
            # Try to get the model by name
            model = replicate.models.get(f"ansavva/{model_name}")
        except:
            # If model not found, create it
            model = replicate.models.create(
                owner="ansavva",
                name=model_name,
                visibility="private",  # or "private" if you prefer
                hardware="gpu-t4",  # Replicate will override this for fine-tuned models
                description="A fine-tuned FLUX.1 model"
            )
        zip_file_buffer = self.image_service.create_zip(project_id)
        training = replicate.trainings.create(
            version="ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011f3e20e8ea6fa",
            input={
                "input_images": zip_file_buffer,
                "steps": 1000
            },
            destination=f"{model.owner}/{model.name}"
        )
        return training.id

    def check_training_status(self, training_id: str) -> str:
        # Query the training status
        training_status = replicate.trainings.get(training_id)
        status = training_status.status
        return status

    def generate(self, prompt: str, project_id: str) -> Image:
        model_name = self.__get_model_name(project_id)
        model = replicate.models.get(f"ansavva/{model_name}")
        output = replicate.run(
            f"{model.owner}/{model.name}:{model.latest_version.id}",
            input={
                "model": "dev",
                "prompt": prompt,
                "lora_scale": 1,
                "num_outputs": 1,
                "aspect_ratio": "1:1",
                "output_format": "jpg",
                "guidance_scale": 3.5,
                "output_quality": 90,
                "prompt_strength": 0.8,
                "extra_lora_scale": 1,
                "num_inference_steps": 28,
                "disable_safety_checker": True
            }
        )
        # Get the URL of the generated image
        image_url = output[0].url
        # Download the image from the URL
        response = requests.get(image_url)
        # Check if the request was successful
        if response.status_code == 200:
            # Convert the image content into a file-like object
            image_data = BytesIO(response.content)
            file = FileStorage(image_data)
            # Call the upload_image method to upload the image to S3
            image = self.image_service.upload_image(project_id, file, "out.jpg")
            return image
        else:
            raise Exception("Failed to download generated image from Replicate")