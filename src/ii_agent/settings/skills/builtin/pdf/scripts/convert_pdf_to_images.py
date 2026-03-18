import os
import sys

from pdf2image import convert_from_path


# Converts each page of a PDF to a PNG image.


def convert(pdf_path, output_dir, max_dim=1000):
    images = convert_from_path(pdf_path, dpi=200)

    for i, image in enumerate(images):
        output_image = image
        # Scale image if needed to keep width/height under `max_dim`
        width, height = output_image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            output_image = output_image.resize((new_width, new_height))

        image_path = os.path.join(output_dir, f"page_{i + 1}.png")
        output_image.save(image_path)
        print(f"Saved page {i + 1} as {image_path} (size: {output_image.size})")

    print(f"Converted {len(images)} pages to PNG images")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: convert_pdf_to_images.py [input pdf] [output directory]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_directory = sys.argv[2]
    convert(pdf_path, output_directory)
