from io import BytesIO
from typing import List, Optional
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from PIL import Image
import io

from src.models.story_page import StoryPage


class PDFExportService:
    """Service for exporting storybooks to PDF format"""

    def __init__(self):
        self.page_size = letter  # Default to US Letter (8.5" x 11")
        self.margin = 0.75 * inch
        self.styles = getSampleStyleSheet()

    def generate_storybook_pdf(
        self,
        story_title: str,
        child_name: str,
        pages: List[StoryPage],
        page_images: dict,  # Dict mapping page_id to image bytes
        page_size: str = "letter"
    ) -> BytesIO:
        """
        Generate a PDF storybook

        Args:
            story_title: Title of the story
            child_name: Name of the child (main character)
            pages: List of StoryPage objects
            page_images: Dictionary mapping page._id to image bytes
            page_size: "letter" or "a4"

        Returns:
            BytesIO containing the PDF
        """
        # Set page size
        if page_size.lower() == "a4":
            self.page_size = A4
        else:
            self.page_size = letter

        # Create PDF buffer
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=self.page_size)

        # Get dimensions
        width, height = self.page_size

        # Generate cover page
        self._draw_cover_page(pdf, story_title, child_name, width, height)

        # Generate story pages
        for page in sorted(pages, key=lambda p: p.page_number):
            pdf.showPage()  # Start new page

            # Get image for this page
            image_bytes = page_images.get(page._id)

            self._draw_story_page(
                pdf,
                page.page_number,
                page.page_text,
                image_bytes,
                width,
                height
            )

        # Add branding footer to last page
        self._draw_branding_footer(pdf, width, height)

        # Finalize PDF
        pdf.save()
        buffer.seek(0)

        return buffer

    def _draw_cover_page(self, pdf: canvas.Canvas, title: str, child_name: str, width: float, height: float):
        """Draw the cover page"""
        # Background
        pdf.setFillColorRGB(0.95, 0.95, 1.0)  # Light blue background
        pdf.rect(0, 0, width, height, fill=True, stroke=False)

        # Title
        pdf.setFillColorRGB(0.1, 0.1, 0.4)  # Dark blue text
        pdf.setFont("Helvetica-Bold", 36)
        title_text = title or "Untitled Story"
        title_width = pdf.stringWidth(title_text, "Helvetica-Bold", 36)
        pdf.drawString((width - title_width) / 2, height - 2 * inch, title_text)

        # Subtitle
        pdf.setFont("Helvetica", 24)
        subtitle = f"A Story for {child_name}"
        subtitle_width = pdf.stringWidth(subtitle, "Helvetica", 24)
        pdf.drawString((width - subtitle_width) / 2, height - 2.75 * inch, subtitle)

        # Branding
        pdf.setFont("Helvetica-Oblique", 14)
        branding = "Created with Storybook"
        branding_width = pdf.stringWidth(branding, "Helvetica-Oblique", 14)
        pdf.drawString((width - branding_width) / 2, 1.5 * inch, branding)

        # Decorative elements
        pdf.setStrokeColorRGB(0.6, 0.6, 0.8)
        pdf.setLineWidth(2)
        pdf.line(self.margin, height - 3.5 * inch, width - self.margin, height - 3.5 * inch)

    def _draw_story_page(
        self,
        pdf: canvas.Canvas,
        page_number: int,
        text: str,
        image_bytes: Optional[bytes],
        width: float,
        height: float
    ):
        """Draw a story page with image and text"""
        # Reset background to white
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(0, 0, width, height, fill=True, stroke=False)

        # Calculate layout
        image_area_height = height * 0.65  # 65% for image
        text_area_height = height * 0.25   # 25% for text
        footer_height = height * 0.10      # 10% for footer

        # Draw illustration if available
        if image_bytes:
            try:
                # Load image
                img = Image.open(io.BytesIO(image_bytes))

                # Calculate image dimensions to fit
                img_max_width = width - (2 * self.margin)
                img_max_height = image_area_height - self.margin

                # Get aspect ratio
                img_aspect = img.width / img.height

                # Calculate scaled dimensions
                if img_aspect > (img_max_width / img_max_height):
                    # Width is limiting factor
                    img_width = img_max_width
                    img_height = img_width / img_aspect
                else:
                    # Height is limiting factor
                    img_height = img_max_height
                    img_width = img_height * img_aspect

                # Center the image
                x = (width - img_width) / 2
                y = height - self.margin - img_height

                # Draw image
                img_reader = ImageReader(io.BytesIO(image_bytes))
                pdf.drawImage(img_reader, x, y, img_width, img_height)

            except Exception as e:
                # If image fails, draw placeholder
                self._draw_image_placeholder(pdf, width, height, image_area_height)
        else:
            # No image, draw placeholder
            self._draw_image_placeholder(pdf, width, height, image_area_height)

        # Draw text
        text_y_start = height - image_area_height - self.margin
        text_y_end = footer_height + self.margin

        # Create text style
        text_style = ParagraphStyle(
            'StoryText',
            parent=self.styles['Normal'],
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=10
        )

        # Create paragraph
        para = Paragraph(text, text_style)

        # Create frame for text
        text_frame = Frame(
            self.margin,
            text_y_end,
            width - (2 * self.margin),
            text_y_start - text_y_end,
            showBoundary=0
        )

        # Draw text in frame
        text_frame.addFromList([para], pdf)

        # Draw page number
        pdf.setFont("Helvetica", 10)
        pdf.setFillColorRGB(0.5, 0.5, 0.5)
        page_num_text = str(page_number)
        page_num_width = pdf.stringWidth(page_num_text, "Helvetica", 10)
        pdf.drawString((width - page_num_width) / 2, 0.5 * inch, page_num_text)

    def _draw_image_placeholder(self, pdf: canvas.Canvas, width: float, height: float, image_area_height: float):
        """Draw a placeholder when no image is available"""
        placeholder_width = width - (2 * self.margin)
        placeholder_height = image_area_height - self.margin

        x = self.margin
        y = height - self.margin - placeholder_height

        # Draw rectangle
        pdf.setFillColorRGB(0.95, 0.95, 0.95)
        pdf.setStrokeColorRGB(0.7, 0.7, 0.7)
        pdf.rect(x, y, placeholder_width, placeholder_height, fill=True, stroke=True)

        # Draw text
        pdf.setFillColorRGB(0.5, 0.5, 0.5)
        pdf.setFont("Helvetica", 14)
        placeholder_text = "Image not generated"
        text_width = pdf.stringWidth(placeholder_text, "Helvetica", 14)
        pdf.drawString(
            x + (placeholder_width - text_width) / 2,
            y + (placeholder_height / 2),
            placeholder_text
        )

    def _draw_branding_footer(self, pdf: canvas.Canvas, width: float, height: float):
        """Draw branding footer on the last page"""
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColorRGB(0.6, 0.6, 0.6)

        branding_text = "Powered by Storybook - AI-Generated Personalized Children's Stories"
        text_width = pdf.stringWidth(branding_text, "Helvetica-Oblique", 9)
        pdf.drawString((width - text_width) / 2, 0.3 * inch, branding_text)
