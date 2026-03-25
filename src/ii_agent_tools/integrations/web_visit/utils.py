PROMPT = """You are analyzing webpage content. Your task is to extract and process information based on the given instructions.

<webpage_content>
{content}
</webpage_content>

<user_request>
{prompt}
</user_request>

Instructions:
- Extract, organize, and process information from the webpage content based on the user's request
- Provide the response in clear, structured markdown (e.g., with headings, bullet points, tables, or code blocks where relevant)
- Deliver the response in a comprehensive and detailed manner by default
- The output must rely strictly on the webpage content. Do not fabricate, assume, or hallucinate information
- If requested information is not present in the webpage content, explicitly state it as "Not found"
- Do not include any commentary about the process itself—only provide the final result
"""


def get_visit_webpage_prompt(url: str, prompt: str) -> str:
    return PROMPT.format(content=url, prompt=prompt)


def extract_title(soup):
    """Extract title from BeautifulSoup object."""
    title_tag = soup.find("title")
    return title_tag.get_text() if title_tag else ""


def clean_soup(soup):
    """Remove script and style elements from BeautifulSoup object."""
    for script in soup(["script", "style"]):
        script.decompose()
    return soup


def get_text_from_soup(soup):
    """Extract text content from BeautifulSoup object."""
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    return text
