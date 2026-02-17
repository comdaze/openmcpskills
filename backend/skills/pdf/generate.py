"""Entry point for pdf code interpreter execution.

Available packages: pypdf, pdfplumber, reportlab, markitdown, pillow, pypdfium2
The LLM will generate the actual implementation code.
"""
import sys
import os

# Add scripts directory to path
scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
if os.path.isdir(scripts_dir):
    sys.path.insert(0, scripts_dir)

print("PDF Code Interpreter initialized")
print("Available packages: pypdf, pdfplumber, reportlab, markitdown, pillow, pypdfium2")
print("Available scripts:")
print("  - scripts/check_bounding_boxes.py: Check bounding boxes in form fields")
print("  - scripts/check_fillable_fields.py: Check if PDF has fillable form fields")
print("  - scripts/convert_pdf_to_images.py: Convert PDF pages to images")
print("  - scripts/create_validation_image.py: Create validation images")
print("  - scripts/extract_form_field_info.py: Extract form field info to JSON")
print("  - scripts/extract_form_structure.py: Extract form structure")
print("  - scripts/fill_fillable_fields.py: Fill fillable form fields")
print("  - scripts/fill_pdf_form_with_annotations.py: Fill non-fillable forms with annotations")
print("Save output files to /tmp/ for automatic upload.")
