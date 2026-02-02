---
name: calculator
description: Performs mathematical calculations including basic arithmetic, percentages, and common math functions. Use when the user needs to compute numbers, solve math problems, or perform calculations.
license: Apache-2.0
metadata:
  author: Open MCP Skills Team
  version: "1.0.0"
  tags:
    - math
    - utility
    - calculation
---

# Calculator Skill

A comprehensive calculator for performing mathematical operations.

## When to Use

Use this skill when:
- The user needs to perform arithmetic calculations
- Mathematical expressions need to be evaluated
- Percentage or ratio calculations are required
- Unit conversions involving math are needed

## Supported Operations

### Basic Arithmetic
- Addition (+)
- Subtraction (-)
- Multiplication (×)
- Division (÷)
- Modulo (%)

### Advanced Operations
- Exponentiation (power)
- Square root
- Absolute value
- Rounding (floor, ceiling, round)

### Percentage Calculations
- Calculate X% of Y
- What percentage is X of Y
- Increase/decrease by percentage

## Instructions

1. Parse the mathematical expression from the user's request
2. Identify the operation(s) needed
3. Perform the calculation step by step
4. Return the result with the expression shown

### Calculation Format

Always show your work:
```
Expression: 15 + 27
Result: 42
```

For complex calculations:
```
Step 1: 100 × 0.15 = 15 (calculate 15%)
Step 2: 100 + 15 = 115 (add to original)
Result: 115
```

## Examples

**User**: "What is 25 times 4?"
**Response**:
```
Expression: 25 × 4
Result: 100
```

**User**: "Calculate 15% of 200"
**Response**:
```
Expression: 200 × 0.15
Result: 30
```

**User**: "What's the square root of 144?"
**Response**:
```
Expression: √144
Result: 12
```

## Error Handling

- Division by zero: Return an error message explaining it's undefined
- Invalid operations: Ask for clarification
- Overflow: Indicate the number is too large to represent

## Notes

- Use appropriate precision (avoid excessive decimal places)
- For currency calculations, round to 2 decimal places
- Show intermediate steps for complex calculations
