#!/usr/bin/env python3
"""
PPTX Generator Entry Point for Code Interpreter

This script serves as the main entry point when the skill is executed
in AWS Bedrock AgentCore Code Interpreter sandbox.

The LLM will generate code that uses the scripts and utilities provided
in this skill to create, edit, or analyze PowerPoint presentations.
"""

import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

def main():
    """
    Main entry point for code interpreter execution.
    
    The LLM will generate the actual implementation code based on:
    - User requirements
    - Available scripts in scripts/ directory
    - Documentation in SKILL.md, editing.md, pptxgenjs.md
    """
    print("PPTX Generator initialized")
    print("Available utilities:")
    print("  - scripts/thumbnail.py: Generate slide thumbnails")
    print("  - scripts/clean.py: Clean presentation XML")
    print("  - scripts/add_slide.py: Add slides to presentation")
    print("  - scripts/office/: Office file manipulation utilities")
    print("\nReady for LLM-generated code execution")

if __name__ == "__main__":
    main()
