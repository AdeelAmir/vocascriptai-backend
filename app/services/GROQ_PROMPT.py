# def get_classification_prompt() -> str:
#     return """
# You are an expert meeting analyst.

# You will be given the beginning of a meeting transcript.

# Your job is to classify the meeting into exactly ONE of these types:
# - developer_meeting (client + developer/agency discussing bugs, features, modules, screens)
# - lecture (teacher/professor/instructor delivering educational content)
# - interview (job interview, candidate evaluation, HR screening)
# - sales_call (sales pitch, product demo, pricing discussion)
# - hr_meeting (onboarding, performance review, team management)
# - general_discussion (casual discussion, brainstorming, planning, anything else)
# - standup_meeting (daily standup, sprint planning, retrospective)
# - training_session (employee/team training, onboarding training)
# - product_demo (product walkthrough, client demo)
# - legal_meeting (contracts, compliance, legal review)
# - financial_meeting (budgets, forecasts, investor updates)
# - medical_consultation (doctor/patient, therapy session)
# - podcast_interview (casual long-form conversation for content)
# - customer_support (support call, complaint resolution)
# - board_meeting (executive/board level decisions)

# Rules:
# - Read the transcript carefully
# - Pick the SINGLE best matching type
# - If unsure → use general_discussion
# - Do NOT explain your reasoning

# Output Format (STRICT JSON):
# {
#     "type": "meeting_type_here"
# }

# Return ONLY the JSON. No markdown, no extra text.
# """

def get_summary_gen_prompt() -> str:
    return f"""
You are an expert meeting analyst.

You will be given a meeting transcript.

Your job:
1. Generate a concise but complete summary — cover every major topic discussed in maximum 10-15 sentences

Rules for summary:
- Capture all major topics and decisions — do NOT miss anything important
- Keep each point concise — one sentence per topic, no lengthy explanations
- Do NOT add assumptions or invent details
- Use ONLY information from the transcript
- Write the summary in exactly the same language and script used by the transcript
- Do not translate the summary to English or any other language
- Maximum 10-15 sentences total regardless of meeting length

Output Format (STRICT JSON):
{{
    "summary": "complete detailed summary here"
}}

Return ONLY the JSON. No markdown, no extra text.
"""



# def board_meeting_prompt_gen() -> str:
#     return f"""
# You are an expert corporate governance analyst and executive advisor.

# You will be given a PARTIAL board meeting or executive session transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all strategic topics, decisions, approvals, and concerns raised by board members
# 3. Group ALL board points, resolutions, and action items by strategic area
# 4. Generate ONE detailed, actionable prompt per strategic topic or board agenda item

# Grouping Rules:
# - If multiple board points belong to the same strategic area or agenda item → combine into ONE prompt
# - Only create separate prompts for genuinely different strategic areas
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert corporate governance advisor or executive strategist")
# - Write a detailed TASK section that covers:
#     - The strategic topic or board agenda item being discussed
#     - All positions, arguments, and concerns raised by board members
#     - Votes taken and outcomes — approved, rejected, or deferred
#     - Key performance indicators or financial metrics reviewed
#     - Risks and governance concerns raised by any board member
#     - Strategic initiatives approved or rejected with reasoning
#     - Executive accountability assignments and deadlines
#     - Regulatory or compliance matters discussed
#     - Resolutions passed and their exact terms
#     - Next board meeting agenda items or follow-up requirements
# - Prompt must be detailed enough for a corporate secretary or executive team to generate complete board minutes
# - Minimum 10-15 sentences per prompt
# - Cover every board decision and resolution — nothing should be left out

# If NO board content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No board content found", "description": "No clear board meeting or executive discussion content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "resolution" or "strategic_decision" or "governance_concern",
#             "title": "strategic topic or board agenda item",
#             "description": "summary of all board positions, votes, and decisions for this item",
#             "prompt": "complete ready-to-use board minutes prompt covering all points for this agenda item"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def customer_support_prompt_gen() -> str:
#     return f"""
# You are an expert customer experience analyst and support operations specialist.

# You will be given a PARTIAL customer support call transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all customer issues, complaints, and requests discussed
# 3. Group ALL support points, resolutions, and escalations by issue area
# 4. Generate ONE detailed, actionable prompt per customer issue or complaint area

# Grouping Rules:
# - If multiple complaints or requests belong to the same issue area → combine into ONE prompt
# - Only create separate prompts for genuinely different customer issues
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert customer support specialist or CX manager")
# - Write a detailed TASK section that covers:
#     - The customer issue, complaint, or request being discussed
#     - The customer's exact pain point and emotional state if mentioned
#     - Steps the support agent took to investigate or resolve the issue
#     - Any system errors, bugs, or product failures identified
#     - Compensation, refunds, or remedies offered to the customer
#     - Escalations raised and to which team or department
#     - Resolution provided or pending — with timeline if mentioned
#     - Follow-up actions required by support team after the call
#     - Suggested improvements to prevent this issue from recurring
# - Prompt must be detailed enough for a support team to act on and close the ticket without follow-up
# - Minimum 10-15 sentences per prompt
# - Cover every customer complaint and resolution step — nothing should be left out

# If NO support content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No support content found", "description": "No clear customer support issues or complaints were identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "complaint" or "request" or "escalation",
#             "title": "customer issue or complaint area",
#             "description": "summary of the issue, steps taken, and resolution status",
#             "prompt": "complete ready-to-use support prompt covering all points for this issue"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def podcast_interview_prompt_gen() -> str:
#     return f"""
# You are an expert content strategist and podcast producer.

# You will be given a PARTIAL podcast or long-form interview transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all topics, stories, insights, and opinions shared by the guest and host
# 3. Group ALL key moments, quotes, and discussion points by topic or theme
# 4. Generate ONE detailed, actionable content prompt per topic or theme

# Grouping Rules:
# - If multiple discussion points belong to the same topic or theme → combine into ONE prompt
# - Only create separate prompts for genuinely different topics or themes
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert content writer or podcast producer")
# - Write a detailed TASK section that covers:
#     - The topic or theme being discussed
#     - Key insights, opinions, and arguments shared by the guest
#     - Personal stories or experiences mentioned that support the topic
#     - The host's reactions, follow-up questions, and counterpoints
#     - Any controversial or thought-provoking statements made
#     - Actionable advice or takeaways shared for the audience
#     - Recommended content angles for repurposing this segment — blog post, social clip, newsletter
#     - Suggested title, hook, and call-to-action for each content piece
# - Prompt must be detailed enough for a content team to repurpose this segment without listening to the episode
# - Minimum 10-15 sentences per prompt
# - Cover every key insight and story — nothing should be left out

# If NO podcast content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No podcast content found", "description": "No clear podcast or interview content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "insight" or "story" or "content_angle",
#             "title": "topic or theme name",
#             "description": "summary of all key points, insights, and stories for this topic",
#             "prompt": "complete ready-to-use content prompt covering all points for this topic"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def medical_consultation_prompt_gen() -> str:
#     return f"""
# You are an expert medical documentation specialist and clinical analyst.

# You will be given a PARTIAL medical consultation or therapy session transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all symptoms, diagnoses, treatments, and medical concerns discussed
# 3. Group ALL medical points, prescriptions, and follow-up actions by condition or concern area
# 4. Generate ONE detailed, actionable prompt per medical topic or concern area

# Grouping Rules:
# - If multiple symptoms or treatments belong to the same condition or concern → combine into ONE prompt
# - Only create separate prompts for genuinely different medical conditions or concerns
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert medical documentation specialist or clinical advisor")
# - Write a detailed TASK section that covers:
#     - The medical condition, symptom, or concern being discussed
#     - All symptoms reported by the patient and observations made by the doctor
#     - Diagnosis or working diagnosis mentioned
#     - Tests, scans, or investigations ordered
#     - Medications prescribed — name, dosage, frequency, and duration
#     - Lifestyle changes or dietary recommendations given
#     - Referrals to specialists mentioned
#     - Follow-up appointments and monitoring requirements
#     - Any patient concerns or questions raised and how they were addressed
# - Prompt must be detailed enough for a medical team to generate complete clinical notes without follow-up
# - Minimum 10-15 sentences per prompt
# - Cover every medical point and instruction — nothing should be left out

# If NO medical content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No medical content found", "description": "No clear medical consultation content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "diagnosis" or "treatment" or "follow_up",
#             "title": "medical condition or concern area",
#             "description": "summary of all symptoms, diagnoses, and treatments for this condition",
#             "prompt": "complete ready-to-use clinical documentation prompt covering all points for this condition"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def financial_meeting_prompt_gen() -> str:
#     return f"""
# You are an expert financial analyst and business strategist.

# You will be given a PARTIAL financial meeting transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all financial topics, figures, forecasts, and decisions discussed
# 3. Group ALL financial points, risks, and action items by topic or financial area
# 4. Generate ONE detailed, actionable prompt per financial topic or area

# Grouping Rules:
# - If multiple financial points belong to the same budget, forecast, or financial area → combine into ONE prompt
# - Only create separate prompts for genuinely different financial areas
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert financial analyst or CFO advisor")
# - Write a detailed TASK section that covers:
#     - The financial topic, budget area, or investment being discussed
#     - All figures, targets, and benchmarks mentioned
#     - Variances, shortfalls, or overruns identified
#     - Risks and financial concerns raised by any party
#     - Forecasts, projections, or scenarios discussed
#     - Decisions made regarding budgets, investments, or cost cuts
#     - Approvals required and who is responsible
#     - Recommended financial actions and next steps with deadlines
# - Prompt must be detailed enough for a finance team to act on without follow-up questions
# - Minimum 10-15 sentences per prompt
# - Cover every financial point and decision — nothing should be left out

# If NO financial content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No financial content found", "description": "No clear financial topics or discussions were identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "budget" or "forecast" or "investment" or "risk",
#             "title": "financial topic or area",
#             "description": "summary of all financial points, figures, and decisions for this area",
#             "prompt": "complete ready-to-use financial prompt covering all points for this area"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def legal_meeting_prompt_gen() -> str:
#     return f"""
# You are an expert legal analyst and contract specialist.

# You will be given a PARTIAL legal meeting transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all legal topics, clauses, obligations, and concerns discussed
# 3. Group ALL legal points, risks, and action items by topic or contract area
# 4. Generate ONE detailed, actionable prompt per legal topic or contract area

# Grouping Rules:
# - If multiple legal points belong to the same contract section or legal topic → combine into ONE prompt
# - Only create separate prompts for genuinely different legal areas
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert legal counsel or contract specialist")
# - Write a detailed TASK section that covers:
#     - The legal topic, clause, or contract area being discussed
#     - All obligations, rights, and liabilities mentioned for each party
#     - Any disputed clauses or terms that need revision
#     - Compliance requirements or regulatory concerns raised
#     - Deadlines, signatures, or approvals required
#     - Risks identified and mitigation strategies discussed
#     - Recommended changes or additions to the contract or agreement
#     - Next steps and who is responsible for each legal action item
# - Prompt must be detailed enough for a legal team to act on without follow-up questions
# - Minimum 10-15 sentences per prompt
# - Cover every legal point and obligation — nothing should be left out

# If NO legal content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No legal content found", "description": "No clear legal topics or contract discussions were identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "contract_clause" or "compliance" or "legal_action",
#             "title": "legal topic or contract area",
#             "description": "summary of all legal points, obligations, and risks for this area",
#             "prompt": "complete ready-to-use legal prompt covering all points for this area"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def product_demo_prompt_gen() -> str:
#     return f"""
# You are an expert product analyst and solutions consultant.

# You will be given a PARTIAL product demonstration transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all features, workflows, and capabilities demonstrated
# 3. Group ALL audience questions, reactions, objections, and requested changes by product area
# 4. Generate ONE detailed, actionable prompt per product area or feature demonstrated

# Grouping Rules:
# - If multiple questions or reactions belong to the same feature or product area → combine into ONE prompt
# - Only create separate prompts for genuinely different product areas
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert product manager or solutions engineer")
# - Write a detailed TASK section that covers:
#     - The product feature or workflow that was demonstrated
#     - How the audience reacted — interest, confusion, objections, or excitement
#     - All questions asked by the audience about this feature
#     - Any gaps or limitations the audience identified
#     - Customization or changes the audience requested
#     - Competitor comparisons mentioned during the demo
#     - Suggested improvements or follow-up actions based on audience feedback
#     - Next steps agreed upon after the demo for this feature
# - Prompt must be detailed enough for a product team to act on all feedback without follow-up questions
# - Minimum 10-15 sentences per prompt
# - Cover every reaction, question, and request — nothing should be left out

# If NO demo content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No demo content found", "description": "No clear product demonstration content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "feature_feedback" or "objection" or "follow_up",
#             "title": "product feature or area demonstrated",
#             "description": "summary of audience reactions, questions, and requests for this feature",
#             "prompt": "complete ready-to-use prompt covering all feedback and next steps for this feature"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def training_session_prompt_gen() -> str:
#     return f"""
# You are an expert corporate trainer and learning development analyst.

# You will be given a PARTIAL training session transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all training topics, skills, and competencies being taught
# 3. Group ALL learning objectives, demonstrations, and exercises by training module or skill area
# 4. Generate ONE detailed, actionable training prompt per module or skill area

# Grouping Rules:
# - If multiple points belong to the same training module or skill → combine into ONE prompt
# - Only create separate prompts for genuinely different skills or training areas
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume content that was not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert corporate trainer or subject matter expert")
# - Write a detailed TASK section that covers:
#     - The skill, tool, or competency being trained
#     - All steps, procedures, or concepts demonstrated in this module
#     - Common mistakes or pitfalls highlighted by the trainer
#     - Any assessments, quizzes, or practice exercises mentioned
#     - Real-world scenarios or case studies used during training
#     - Key takeaways the trainee must remember
#     - Suggested practice tasks for reinforcement after the session
# - Prompt must be detailed enough for an AI tool to generate complete training material or assessment
# - Minimum 10-15 sentences per prompt
# - Cover every training point — nothing should be left out

# If NO training content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No training content found", "description": "No clear training content or learning objectives were identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "skill" or "module" or "assessment",
#             "title": "training module or skill area name",
#             "description": "summary of all training points covered for this module",
#             "prompt": "complete ready-to-use training prompt covering all points for this module"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def standup_meeting_prompt_gen() -> str:
#     return f"""
# You are an expert agile coach and scrum master analyst.

# You will be given a PARTIAL standup, sprint planning, or retrospective transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all team members who spoke and what they reported
# 3. Group ALL blockers, progress updates, and sprint items by team member or feature area
# 4. Generate ONE detailed, actionable prompt per blocker or sprint item that needs attention

# Grouping Rules:
# - If multiple team members mention the same blocker or feature → combine into ONE prompt
# - Only create separate prompts for genuinely different blockers or sprint items
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert agile developer or scrum master")
# - Write a detailed TASK section that covers:
#     - The blocker, task, or sprint item being discussed
#     - Which team member(s) reported it
#     - Current status — what is done, what is in progress, what is stuck
#     - The exact blocker or dependency causing the delay if mentioned
#     - Suggested resolution steps or who needs to act
#     - Any deadline or sprint end date mentioned
#     - Follow-up actions required before the next standup
# - Prompt must be detailed enough for an AI tool or team member to act on immediately
# - Minimum 10-15 sentences per prompt
# - Cover every blocker and unresolved item — nothing should be left out

# If NO blockers or actionable items are found → return exactly:
# {{"items": [{{"type": "none", "title": "No blockers or action items found", "description": "No blockers, issues, or unresolved sprint items were identified.", "prompt": "No prompt needed"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "blocker" or "in_progress" or "follow_up",
#             "title": "blocker or sprint item name",
#             "description": "summary of the issue, who reported it, and current status",
#             "prompt": "complete ready-to-use prompt to resolve this blocker or sprint item"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def prompt_for_dev() -> str:
#     return f"""
# You are an expert project manager and technical analyst.

# You will be given a PARTIAL meeting transcript between a client and a developer/agency.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all modules, features, or screen areas discussed in this portion
# 3. Group ALL bugs, issues, and feature requests by their module or feature area
# 4. Generate ONE detailed, actionable prompt per module/feature area

# Grouping Rules:
# - If multiple bugs or features belong to the same module, screen, or feature area → combine them into ONE prompt
# - Only create separate prompts if the issues belong to completely different modules or unrelated parts of the system
# - A "module" means: same screen, same feature, or same functional area of the system
# - Do NOT create one prompt per bug — think in terms of modules and features
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume tasks that were not mentioned
# - This may be a partial transcript — extract only what is visible in this portion
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment matching the task (e.g. "Act as a professional full stack web developer")
# - After the role, write a detailed TASK section that covers:
#     - The module or feature area being worked on
#     - All bugs, issues, and feature requests for that module in one place
#     - Exact behavior expected for each issue
#     - Where it needs to be done (which page, screen, component, or function)
#     - Any solution the client mentioned → include it
#     - If no solution was mentioned → suggest the best approach based on context
# - Prompt must be detailed enough that an AI tool like Cursor can implement it without asking follow-up questions
# - Minimum 10-15 sentences per prompt
# - Cover every issue for that module — nothing should be left out

# If NO bugs, errors, or feature requests are found → return exactly:
# {{"items": [{{"type": "none", "title": "No issues or features mentioned", "description": "The client did not mention any bugs, errors, issues, or new feature requests.", "prompt": "No prompt for updation"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "bug" or "feature" or "improvement",
#             "title": "module or feature area name",
#             "description": "summary of all issues discussed for this module",
#             "prompt": "complete ready-to-use prompt covering all issues for this module"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def lecture_prompt_gen() -> str:
#     return f"""
# You are an expert educational content analyst.

# You will be given a PARTIAL lecture or educational session transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all topics, concepts, or subject areas discussed
# 3. Group ALL key points, explanations, and examples by their topic area
# 4. Generate ONE detailed, actionable study prompt per topic area

# Grouping Rules:
# - If multiple points belong to the same topic → combine into ONE prompt
# - Only create separate prompts for genuinely different topics
# - Extract ONLY what was explicitly discussed in this portion
# - Do NOT invent or assume content that was not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert tutor in this subject")
# - Write a detailed TASK section that covers:
#     - The topic or concept being explained
#     - All key points, definitions, and examples discussed
#     - Any exercises or practice problems mentioned
#     - Suggested follow-up questions for deeper understanding
# - Prompt must be detailed enough for an AI tool to generate comprehensive study material
# - Minimum 10-15 sentences per prompt

# If NO educational content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No educational content found", "description": "No clear educational content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "concept" or "topic" or "exercise",
#             "title": "topic or concept name",
#             "description": "summary of all key points discussed for this topic",
#             "prompt": "complete ready-to-use study prompt covering all points for this topic"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def interview_prompt_gen() -> str:
#     return f"""
# You are an expert HR analyst and interview evaluator.

# You will be given a PARTIAL interview transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all questions asked and answers given
# 3. Group responses by skill area or evaluation category
# 4. Generate ONE detailed evaluation prompt per category

# Grouping Rules:
# - Group related questions and answers into ONE prompt
# - Only separate prompts for genuinely different skill areas
# - Extract ONLY what was explicitly discussed
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert HR evaluator")
# - Write a detailed TASK section that covers:
#     - The skill area or category being evaluated
#     - All questions asked in this area
#     - Candidate's responses and key points made
#     - Strengths and weaknesses identified
#     - Suggested follow-up questions or evaluation criteria
# - Minimum 10-15 sentences per prompt

# If NO interview content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No interview content found", "description": "No clear interview content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "technical" or "behavioral" or "general",
#             "title": "skill area or evaluation category",
#             "description": "summary of questions and responses for this category",
#             "prompt": "complete ready-to-use evaluation prompt for this category"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def sales_call_prompt_gen() -> str:
#     return f"""
# You are an expert sales analyst.

# You will be given a PARTIAL sales call transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all products, objections, requirements, and commitments discussed
# 3. Group ALL points by topic area
# 4. Generate ONE detailed, actionable follow-up prompt per topic area

# Grouping Rules:
# - Group related discussion points into ONE prompt
# - Only separate prompts for genuinely different topics
# - Extract ONLY what was explicitly discussed
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert sales strategist")
# - Write a detailed TASK section that covers:
#     - The product, service, or topic discussed
#     - Customer requirements and pain points mentioned
#     - Objections raised and how they were handled
#     - Commitments or next steps agreed upon
#     - Suggested follow-up actions
# - Minimum 10-15 sentences per prompt

# If NO sales content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No sales content found", "description": "No clear sales content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "requirement" or "objection" or "follow_up",
#             "title": "topic or discussion area",
#             "description": "summary of all points discussed for this area",
#             "prompt": "complete ready-to-use follow-up prompt for this area"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def hr_meeting_prompt_gen() -> str:
#     return f"""
# You are an expert HR analyst.

# You will be given a PARTIAL HR meeting transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all HR topics, concerns, and action points discussed
# 3. Group ALL points by topic area
# 4. Generate ONE detailed, actionable prompt per topic area

# Grouping Rules:
# - Group related HR points into ONE prompt
# - Only separate prompts for genuinely different topics
# - Extract ONLY what was explicitly discussed
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment (e.g. "Act as an expert HR manager")
# - Write a detailed TASK section that covers:
#     - The HR topic or concern being addressed
#     - All points, issues, and decisions discussed
#     - Action items and responsibilities assigned
#     - Deadlines or follow-up dates mentioned
#     - Recommended next steps
# - Minimum 10-15 sentences per prompt

# If NO HR content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No HR content found", "description": "No clear HR content was identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "action_item" or "concern" or "decision",
#             "title": "HR topic or concern area",
#             "description": "summary of all points discussed for this area",
#             "prompt": "complete ready-to-use HR action prompt for this area"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """

# def general_discussion_prompt_gen() -> str:
#     return f"""
# You are an expert meeting analyst.

# You will be given a PARTIAL general discussion or meeting transcript.

# Your job is to:
# 1. Carefully read this portion of the transcript
# 2. Identify all topics, decisions, and action points discussed
# 3. Group ALL points by topic area
# 4. Generate ONE detailed, actionable prompt per topic area

# Grouping Rules:
# - Group related discussion points into ONE prompt
# - Only separate prompts for genuinely different topics
# - Extract ONLY what was explicitly discussed
# - Do NOT invent or assume anything not mentioned
# - Output the title, description, and prompt content in DAY TO DAY ENGLISH LANGUAGE only

# Rules for the generated prompt field:
# - Start with a ROLE assignment matching the discussion context
# - Write a detailed TASK section that covers:
#     - The topic or discussion area
#     - All key points and decisions made
#     - Action items and who is responsible
#     - Any deadlines or next steps mentioned
#     - Recommended follow-up actions
# - Minimum 10-15 sentences per prompt

# If NO actionable content is found → return exactly:
# {{"items": [{{"type": "none", "title": "No actionable content found", "description": "No clear action items or decisions were identified.", "prompt": "No prompt for this section"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "decision" or "action_item" or "discussion_point",
#             "title": "topic or discussion area",
#             "description": "summary of all points discussed for this area",
#             "prompt": "complete ready-to-use action prompt for this area"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """



# def get_prompt_for_type(meeting_type: str) -> str:
#     prompt_map = {
#         "developer_meeting": prompt_for_dev(),
#         "lecture": lecture_prompt_gen(),
#         "interview": interview_prompt_gen(),
#         "sales_call": sales_call_prompt_gen(),
#         "hr_meeting": hr_meeting_prompt_gen(),
#         "general_discussion": general_discussion_prompt_gen(),
#         "standup_meeting": standup_meeting_prompt_gen(),
#         "training_session": training_session_prompt_gen(),
#         "product_demo": product_demo_prompt_gen(),
#         "legal_meeting": legal_meeting_prompt_gen(),
#         "financial_meeting": financial_meeting_prompt_gen(),
#         "medical_consultation": medical_consultation_prompt_gen(),
#         "podcast_interview": podcast_interview_prompt_gen(),
#         "customer_support": customer_support_prompt_gen(),
#         "board_meeting": board_meeting_prompt_gen(),
#     }
#     return prompt_map.get(meeting_type, general_discussion_prompt_gen())


# def prompt_plus_gen_merge() -> str:
#     return f"""
# You are an expert project manager and technical analyst.

# You will be given a list of prompts extracted from different parts of the same meeting transcript.
# These prompts may contain duplicate or overlapping modules because the transcript was processed in chunks.

# Your job is to:
# 1. Read all the provided prompts carefully
# 2. Identify prompts that belong to the same module or feature area
# 3. Merge them into ONE single, comprehensive prompt per module
# 4. Remove any duplicates or redundant items
# 5. Ensure the final output covers everything from all chunks — nothing should be lost

# Merging Rules:
# - If two or more prompts are about the same module or feature area → merge into ONE prompt
# - If two modules are clearly about the same screen or system area, merge them even if their titles differ
# - The merged prompt must include ALL details from all the individual prompts for that module
# - Do NOT drop any issue, bug, or feature request during merging
# - Do NOT add anything new that was not in the original prompts
# - Do NOT generate a prompt for items where the client confirmed the work is already complete or done — exclude them entirely
# - If an item has type "none" → discard it, do not include in final output
# - Only keep prompts separate if they are genuinely about different modules
# - Output the merged prompt should be in DAY TO DAY ENGLISH LANGUAGE

# Rules for the merged prompt field:
# - Start with a ROLE assignment matching the task
# - Write a comprehensive TASK section covering all issues for that module from all chunks
# - Prompt must be detailed enough that an AI tool like Cursor can implement it without asking follow-up questions
# - Minimum 10-15 sentences per merged prompt

# If the input contains only "none" type items → return exactly:
# {{"items": [{{"type": "none", "title": "No issues or features mentioned", "description": "The client did not mention any bugs, errors, issues, or new feature requests.", "prompt": "No prompt for updation"}}]}}

# Output Format (STRICT JSON):
# {{
#     "items": [
#         {{
#             "type": "bug" or "feature" or "improvement",
#             "title": "module or feature area name",
#             "description": "summary of all issues for this module",
#             "prompt": "complete merged ready-to-use prompt covering all issues for this module"
#         }}
#     ]
# }}

# Return ONLY the JSON. No markdown, no extra text.
# """
