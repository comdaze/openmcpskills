"""Entry point for docx code interpreter execution.

Available packages: python-docx, markitdown
The LLM will generate the actual implementation code.
"""
import sys
import os

# Add scripts directory to path
scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
if os.path.isdir(scripts_dir):
    sys.path.insert(0, scripts_dir)

print("DOCX Code Interpreter initialized")
print("Available packages: python-docx, markitdown")
print("Save output files to /tmp/ for automatic upload.")
