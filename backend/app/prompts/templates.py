# This file holds reusable LLM templates for the AI Interview Coach.

EVALUATE_ANSWER_PROMPT = """
You are an expert technical interviewer evaluating a candidate's answer.
Question asked: {question}
Candidate's answer: {answer}

Please evaluate the answer and provide constructive feedback.
"""

EXTRACT_RESUME_INFO_PROMPT = """
Extract the candidate's skills, experience, projects, and education from the
following raw resume text.
If any section is missing, provide an empty list for that section.
Raw Resume Text:
{text}
"""

EXTRACT_JD_INFO_PROMPT = """
Extract the role title, required skills, and key responsibilities from the
following raw job description text.
Raw Job Description Text:
{text}
"""
