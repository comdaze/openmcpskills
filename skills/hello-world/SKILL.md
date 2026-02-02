---
name: hello-world
description: A simple greeting skill that generates personalized hello messages in multiple languages. Use when the user wants to greet someone or needs a friendly welcome message.
license: Apache-2.0
metadata:
  author: Open MCP Skills Team
  version: "1.0.0"
  tags:
    - demo
    - greeting
    - multilingual
---

# Hello World Skill

A friendly greeting skill that creates personalized messages in various languages.

## When to Use

Use this skill when:
- The user wants to greet someone
- A welcome message is needed
- The user wants to say hello in different languages

## Supported Languages

- English: "Hello"
- Spanish: "Hola"
- French: "Bonjour"
- German: "Hallo"
- Chinese: "你好"
- Japanese: "こんにちは"
- Italian: "Ciao"
- Portuguese: "Olá"
- Korean: "안녕하세요"
- Arabic: "مرحبا"

## Instructions

1. Ask the user for the name they want to greet (if not provided)
2. Ask for the preferred language (default to English if not specified)
3. Generate the greeting in the format: "[Greeting], [Name]!"

## Examples

**User**: "Say hello to Alice in French"
**Response**: "Bonjour, Alice!"

**User**: "Greet the team in Japanese"
**Response**: "こんにちは, Team!"

**User**: "Welcome message for new users"
**Response**: "Hello, New User! Welcome aboard!"

## Notes

- Always be warm and friendly in tone
- If the language is not in the supported list, default to English
- For formal contexts, consider adding a polite suffix
