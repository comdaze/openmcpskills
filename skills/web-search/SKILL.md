---
name: web-search
description: Searches the web for current information, news, documentation, and answers to questions. Use when the user needs up-to-date information that may not be in your training data.
license: Apache-2.0
compatibility: Requires network access to search APIs
metadata:
  author: Open MCP Skills Team
  version: "1.0.0"
  tags:
    - search
    - web
    - research
    - information
allowed-tools: WebFetch, WebSearch
---

# Web Search Skill

A skill for searching the web and retrieving current information.

## When to Use

Use this skill when:
- The user asks about recent events or news
- Current pricing, availability, or status is needed
- Documentation or official sources need to be referenced
- The information might have changed since training data cutoff
- User explicitly asks to "search" or "look up" something

## Instructions

### Search Process

1. **Understand the Query**
   - Identify what information the user needs
   - Determine if it requires current/real-time data
   - Formulate an effective search query

2. **Perform the Search**
   - Use the WebSearch tool to find relevant results
   - Consider multiple search queries if needed
   - Look for authoritative sources

3. **Evaluate Results**
   - Check source credibility
   - Verify information across multiple sources when possible
   - Note the date of the information

4. **Present Findings**
   - Summarize the key information
   - Cite sources with URLs
   - Indicate when information was last updated if available

### Search Query Tips

- Use specific keywords rather than full sentences
- Include relevant qualifiers (year, location, version)
- Use quotes for exact phrases
- Add "official" or "documentation" for authoritative sources

## Examples

**User**: "What's the current version of Python?"

**Process**:
1. Search: "Python latest version 2024"
2. Find official python.org source
3. Report: "Python 3.12.x is the current stable version (as of [date]). Source: python.org"

**User**: "Find documentation for FastAPI"

**Process**:
1. Search: "FastAPI official documentation"
2. Locate fastapi.tiangolo.com
3. Provide link and summary of documentation structure

**User**: "What happened in tech news today?"

**Process**:
1. Search: "technology news [today's date]"
2. Aggregate from multiple tech news sources
3. Summarize top stories with sources

## Response Format

```
## Search Results for: [query]

### Summary
[Brief summary of findings]

### Sources
1. [Source Title](URL) - [Brief description]
2. [Source Title](URL) - [Brief description]

### Details
[Detailed information from search results]

---
*Last searched: [timestamp]*
```

## Limitations

- Cannot access paywalled content
- Results depend on search API availability
- May not have access to very recent events (minutes old)
- Cannot verify all information is accurate

## Notes

- Always cite sources
- Indicate uncertainty when information is unclear
- Suggest the user verify critical information
- Respect rate limits on search APIs
