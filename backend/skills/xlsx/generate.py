"""Entry point for xlsx code interpreter execution.

Available packages: openpyxl, pandas, markitdown
The LLM will generate the actual implementation code.
"""
import sys
import os

# Add scripts directory to path
scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
if os.path.isdir(scripts_dir):
    sys.path.insert(0, scripts_dir)

print("XLSX Code Interpreter initialized")
print("Available packages: openpyxl, pandas, markitdown")
print("Available scripts:")
print("  - scripts/recalc.py: Recalculate Excel formulas using LibreOffice")
print("  - scripts/office/: Office file manipulation utilities")
print("Save output files to /tmp/ for automatic upload.")
