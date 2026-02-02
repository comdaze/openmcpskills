---
name: code-review
description: Reviews code for quality, bugs, security issues, and best practices. Use when the user wants feedback on their code, needs a code audit, or wants to improve code quality.
license: Apache-2.0
metadata:
  author: Open MCP Skills Team
  version: "1.0.0"
  tags:
    - code
    - review
    - quality
    - security
    - best-practices
allowed-tools: Read, Grep, Glob
---

# Code Review Skill

A comprehensive code review skill that analyzes code for quality, security, and best practices.

## When to Use

Use this skill when:
- The user asks to review their code
- Code quality assessment is needed
- Security vulnerabilities need to be identified
- Best practices feedback is requested
- Pull request reviews are needed

## Review Categories

### 1. Code Quality
- Readability and clarity
- Code organization and structure
- Naming conventions
- Comments and documentation
- DRY (Don't Repeat Yourself) principle
- SOLID principles adherence

### 2. Bug Detection
- Logic errors
- Off-by-one errors
- Null/undefined handling
- Race conditions
- Resource leaks
- Edge cases

### 3. Security Analysis
- Input validation
- SQL injection vulnerabilities
- XSS (Cross-Site Scripting)
- Authentication/authorization issues
- Sensitive data exposure
- Insecure dependencies

### 4. Performance
- Algorithm efficiency
- Memory usage
- Database query optimization
- Caching opportunities
- Unnecessary computations

### 5. Best Practices
- Language-specific idioms
- Framework conventions
- Error handling patterns
- Testing coverage
- Logging practices

## Instructions

### Review Process

1. **Understand Context**
   - What is the code supposed to do?
   - What language/framework is used?
   - What's the scope of the review?

2. **Read Through Code**
   - Get overall understanding first
   - Note initial observations
   - Identify the main logic flow

3. **Detailed Analysis**
   - Go through each function/method
   - Check for issues in each category
   - Note both problems and good practices

4. **Prioritize Findings**
   - Critical: Security vulnerabilities, bugs
   - High: Performance issues, major code smells
   - Medium: Best practice violations
   - Low: Style/formatting suggestions

5. **Provide Feedback**
   - Be constructive and specific
   - Explain why something is an issue
   - Suggest concrete improvements
   - Include code examples when helpful

### Feedback Format

```markdown
## Code Review Summary

**File(s) Reviewed**: [filename(s)]
**Language**: [language]
**Overall Assessment**: [Good/Needs Improvement/Critical Issues]

### Critical Issues 🔴
[List critical security or bug issues]

### High Priority 🟠
[List important improvements needed]

### Medium Priority 🟡
[List recommended changes]

### Low Priority 🟢
[List minor suggestions]

### Positive Observations ✅
[Highlight good practices found]

### Suggested Improvements
[Specific code examples and fixes]
```

## Examples

**User**: "Review this Python function"
```python
def get_user(id):
    query = "SELECT * FROM users WHERE id = " + id
    return db.execute(query)
```

**Review**:
```markdown
## Code Review Summary

**Overall Assessment**: Critical Issues Found

### Critical Issues 🔴

1. **SQL Injection Vulnerability** (Line 2)
   - Direct string concatenation with user input
   - Allows attackers to execute arbitrary SQL

   **Fix**:
   ```python
   def get_user(id: int) -> User:
       query = "SELECT * FROM users WHERE id = %s"
       return db.execute(query, (id,))
   ```

### Medium Priority 🟡

2. **Missing Type Hints**
   - Add type annotations for better code clarity

3. **No Input Validation**
   - Validate that id is a positive integer

4. **SELECT * Usage**
   - Specify required columns explicitly
```

## Language-Specific Guidelines

### Python
- Follow PEP 8 style guide
- Use type hints (PEP 484)
- Prefer f-strings for formatting
- Use context managers for resources

### JavaScript/TypeScript
- Use strict equality (===)
- Avoid var, prefer const/let
- Handle promises properly
- Use TypeScript types

### Go
- Handle all errors
- Use defer for cleanup
- Follow effective Go guidelines
- Keep functions focused

### Rust
- Use proper error handling (Result/Option)
- Avoid unnecessary clones
- Follow ownership patterns
- Use appropriate lifetimes

## Notes

- Be respectful and constructive
- Focus on the code, not the person
- Acknowledge good practices
- Provide learning resources when helpful
- Consider the context and constraints
