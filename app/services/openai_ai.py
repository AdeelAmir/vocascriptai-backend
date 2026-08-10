import json
from typing import TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from app.services.GEMINI_PROMPT import (
    get_summary_gen_prompt,
    get_master_prompt,
)


# ************************************** Pydantic Schemas ******************************************

class GeneratedSummary(BaseModel):
    summary: str = Field(..., description="Concise summary of the provided transcript")
    model_config = {"extra": "forbid"}


class MeetingPromptItem(BaseModel):
    type: str = Field(..., description="Short lowercase label describing the topic type e.g. bug, feature, setup, discussion, decision, action, improvement, testing, deployment, reporting, planning")
    title: str = Field(..., description="Specific title of the topic — maximum 5-7 words, must clearly identify the module or topic")
    description: str = Field(..., description="One or two sentences MAX summarizing what this topic covers. Keep it very short.")
    prompt: str = Field(..., description="Complete, detailed, ready-to-use actionable prompt. Must be long and comprehensive, minimum 10-15 sentences.")
    model_config = {"extra": "forbid"}


class MeetingPromptOutput(BaseModel):
    items: list[MeetingPromptItem] = Field(..., description="List of extracted prompt items — one per unique topic")
    model_config = {"extra": "forbid"}


# ***************************************** STATE ********************************************

class STATE(TypedDict, total=False):
    text: str
    want_summary: bool
    want_prompt: bool
    generated_summary: str
    generated_prompt: list
    summary_error: str
    prompt_error: str


# ***************************************** Builder ********************************************

def build_ai_agent(api_key: str, model: str = "gpt-4o-mini"):
    """Build and return a compiled OpenAI agent."""

    summary_llm = ChatOpenAI(
        model=model,
        temperature=0.4,
        api_key=api_key,
    ).with_structured_output(GeneratedSummary)

    prompt_llm = ChatOpenAI(
        model=model,
        temperature=0,
        api_key=api_key,
    ).with_structured_output(MeetingPromptOutput)

    # ── Nodes ──────────────────────────────────────────────────────────────

    def summary_node(state: STATE) -> dict:
        if not state.get("want_summary", False):
            return {}
        try:
            result = summary_llm.invoke([
                ("system", get_summary_gen_prompt()),
                ("user", state["text"]),
            ])
            return {"generated_summary": result.summary}
        except Exception as e:
            print(f"[ERROR] summary_node failed: {e}")
            return {"generated_summary": "", "summary_error": f"OpenAI summary generation failed: {e}"}

    def prompt_node(state: STATE) -> dict:
        if not state.get("want_prompt", False):
            return {}
        try:
            result = prompt_llm.invoke([
                ("system", get_master_prompt()),
                ("user", state["text"]),
            ])
            real_items = [
                item.model_dump()
                for item in result.items
                if item.type != "none"
            ]
            print(f"[OpenAI] Generated {len(real_items)} prompt(s)")
            return {"generated_prompt": real_items}
        except Exception as e:
            print(f"[ERROR] prompt_node failed: {e}")
            return {"generated_prompt": [], "prompt_error": f"OpenAI action-item generation failed: {e}"}

    # ── Graph ───────────────────────────────────────────────────────────────

    graph = StateGraph(state_schema=STATE)
    graph.add_node("summary_node", summary_node)
    graph.add_node("prompt_node", prompt_node)

    graph.add_edge(START, "summary_node")
    graph.add_edge(START, "prompt_node")
    graph.add_edge("summary_node", END)
    graph.add_edge("prompt_node", END)

    return graph.compile()



# ***************************************** TESTING AREA ********************************************

# text = """
# Speaker A
# Yeah, I can hear you. Okay, so what I wanted to talk about is the vacation part. Can you hear me okay? Can you see my screen? Okay, so here when you choose an employee, it's still in this one. So here when you choose your employee, you have three types of holidays. The holidays and the holidays days off and the senior or senior scheme or care days. So the first one, this is government dedicated holiday. So this one, it belongs to a certain role where you get 25 days no matter who you are as an employee in Denmark. So when you make the office standards or the unions,

# Speaker B
# It.

# Speaker A
# So these 25 holidays belongs to the government holidays. So if you choose over here that they have care days or senior days or holidays off, if you choose, yes. Then on each employee you have to. It will pop up under the employee information how many days they get specifically. So they cannot be mixed up in the same calculation. Because this one, it has something to do with the salary later on, but they don't. They're. They're just. They just minus the hours that you didn't come and that's it. But the 25 days, it has a big calculation behind it where you get an extra percentage on your salary if you function every month. So it's very important to keep them separate. So when you. When you have the employee and you make the vacation. Here, Then if you choose the holidays here, then this one have to show how many days you've earned of those 25 days. Because each month you earn 2.08 days. So each month the first it have to go up 2.08. And if you. If you take from that those days, it have to calculate from out from that. But if you choose the other one, it cannot show the same thing here. And this is what's missing. These two are missing this. This have to change to show how many days are left of the days you were dedicated in the beginning from your profile. Does that make sense? Okay, so if they didn't give you anything, you can't use them. But if they gave you usually it will be one week. It won't be more than this. It can. It can't. In holidays often will be usually be one week. So five days if you are full time. But of course if you are part time, that goes down accordingly. Then one week. If you. If you only work three days a week, then that's only three days. So depending on how much the company gave you from that, it will show here 5. And then if you take from that, it will. It will calculate it from that so if you take one, there will be four left. But the care and senior days, it's something else. Because if you. If you are. If you have a baby in Denmark and then you get one year home with the baby, but if you decide I only want nine months, I can keep those three months as care days and then I can use it whenever, until the baby I think is 14 years old or something like that. So then, then it will say those three months in your profile and then you can use from it, but it will not. It will not calculate from. From anywhere other than. Than the. The field under the employee. So it have to move accordingly and, and calculate from. Yeah. Did you have a question?

# Speaker B
# I. I understand it. Can you repeat the process one more time from start?

# Speaker A
# Yes, of course. If you have the holidays here, then this is the 25 days. That's. That comes from the unions and the office standards. This is the. It's a government rule that every employee In Denmark gets 25 days. Which means this, this holiday year, it runs from the 1st of September to the 31st of August, every single year. And if you are hired, you can see here employee date. That's because this employee is hired 1 December 2025, which means September, November, September, October, November. They were not in the company, which means they did not earn those 2.08 days for those months. Which means when they start the 1st of December, it won't. It won't start with 6.24 days. It will start with 0. Because they didn't earn anything unless they earned it in a previous work. But then it's being transferred. Then those days will be transferred when they start.

# Speaker B
# Okay?

# Speaker A
# So if you, if you want to have vacation and you. You choose holidays, it have to calculate from those days you've earned. And then it will say, then you will put. Because you can. You can have several years where you can move your vacation. So if I didn't take all my vacation last year, I can move those days with me into the new year. So I can choose. Do I want to spend it from last year? How much do I have left from last year? Do I want to spend it from the year before? I can choose over here. So if I choose it from this year and I say I want to have two days holiday, it's going to calculate two days. And then here it's. This is not working right now. We need to fix this tool. It will say, okay, if you had 45.83 days and you took two days, then the missing balance, which means what is left now? So it should be this number minus this number. Then it should show here how much is left.

# Speaker B
# Okay.

# Speaker A
# And. But if you chose it from here, it cannot show you from the 25 days. It has to show you from the field in your profile where the company dedicated you a week.

# Speaker B
# Okay. Okay.

# Speaker A
# Yeah.

# Speaker B
# This employees did not start from the start of the year. After a few months.

# Speaker A
# Yeah, he.

# Speaker B
# He is going to earn the same 25 vacations per year.

# Speaker A
# So legally everyone has the right for 25 days. But since he didn't start the 1st of September, he started the 1st of December. This company is not legally required to give him those first three months. If he had another work and he was there September, October, November, then he earned the days and he can move it with him, but only the days, which means it will affect Mac time because it's the hours we're talking about. So he can move it with him when he starts, but he didn't earn it in this company. But if he didn't work at all, if he came out of school and he's starting, then he did. He does not have those days at all. It will start from zero.

# Speaker B
# Start from zero. But the question is, for the 25, what would be the max number of holidays he can take?

# Speaker A
# He can take the 25 because he's legally required to, but he have to pay himself for the first three. Okay. Which means his salary will be deducted.

# Speaker B
# Okay.

# Speaker A
# So. So for example, it's supposed to show you. It's all supposed to be working in this one. But. But the holidays off and, and care days, I can see that it's not moving to the right field. But the calculation for this, this should all be working. But of course, I need you to check it too. That it is actually deducting. Correct. Also, if you have a, If I have a holiday, it's not. It's supposed to register. If I have a whole week off, five days, and I'm not checking in and checking out, it's not supposed to deduct hours because you got it from here. So we need to check that this is. It's working as well. But what was my point here? What did you ask?

# Speaker B
# No, I am here.

# Speaker A
# I. Yeah, yeah. My. If. If, if, for example, he. If it's saying 10 days here and he's taking 11, then it's supposed to register that 10 of them is paid and one he have to pay for. This is supposed to be working as well. So it will deduct the salary and the time.

# Speaker B
# Okay.

# Speaker A
# Okay. And then the other thing I just wanted to go over with you really quick. One second, one second. Let me just write something. Yeah, it's about the, the reports, When we do the reports in Mac time. But I don't have any information in my. Under this employee. I don't have any check in and check out. So I can't really see it. I can't see how it's coming up. Do you have anything under your employee where you can press this and. It. Yeah, I can see it. Yeah. Can you send me this file afterwards? Okay, so basically what this means is you have first of all the company ID and the employee id because you need to know which employee and which company you're transferring your information from. And then from the, it will say from the start of June. It's this period from the start of June to the end of June. And then you have the sequence number from this, from this approved period and the export version it's number one because there was no corrections in it. And then here, this is the interesting part. So the one that says normal, this is actually how many hours you hire to work. So let's say this is a function app which means if they're full time it's 160.33 hours but in minutes. And this, this has no value in for a function app because they're always hired on at the same amount of hours. But it still have to appear that this is their, their hours in minutes. The OT50. This means over time the 150% which means if, if they didn't if they in, in unions or office standards have the first two hours as overtime is 30% then this should say 30, not 50. This have to move accordingly. And I don't think it does. I think this is hard, hard coded into 50 but it can't be because the percentage have to follow what it actually says. So and here this person had 60 minutes overtime for the 50. So there should be one more field that says under J it should say the percentages because each one of them have certain percentages because it have to have more fields than this. And I. And we need to check if all the fields are there. So they have to be the normal one. Then they have to be two for overtime, one for the first type of percentages and one for the next type of percentages.

# Speaker B
# Basically we have overtime percentage and we have do we have overtime two diversity?

# Speaker A
# No, we have two because in, in the office and units union place where we make the rules there's two types. The first Two hours or it's saying you can choose how many hours for the small percentage and how many for the big percentage. So it will usually be two hours, 50%. And then after that up till five, you will get a hundred percent over time. So there have to be two. And then, and then it will have the short hours. And this again, if it's functional, it has no value because you will not be deducted your salary. But if you are an hourly employee, the normal one will say it's important to have the normal one because this means this is the hours you're hired to to be here. And, and if you have short hours, it will be deducting your salary. So we have to have these fields. But there's missing a lot. I can see there's missing a lot here. So I have to send you the list to make. So we need to check that all these fields are there and then we need to add the percentages. Because for example, the whole part about if you're working night or evening, remember we have a percentages there too. And if you're working weekends and if you're working on a, on a holiday, a business holiday, like for example, Christmas. Remember we have all that in in standards and we have percentages on all of that. So we have to show them it's because this is the numbers that goes to salary. So they have to know this is the numbers. This is how many minutes they worked on that day and this is how many, how much extra they're getting on top of their salary. So when they move to max to make learn, it's saying this is the salary they're getting. And now when it's saying 50% that means 50% of this number.

# Speaker B
# Yeah.

# Speaker A
# You understand what how it works?

# Speaker B
# Yeah, yeah. You understand Basically this sheet is incomplete. Kind of incomplete.

# Speaker A
# Yeah.

# Speaker B
# Showing couple of things, but there are a couple of of mode like percentages are not displaying. We need to display the sequence number, we need to display employee ID and the OT overtime 50 is hard coded. We need to make it dynamic. So whatever the percentage of overtime. But they, but there is an issue since the overtime percentages are two how we can make it dynamic.

# Speaker A
# So I think we shouldn't call it OT50 here because we just need to show that it's overtime. So call it OT and then and the next overtime also ot. But the percentages should be in J. So if it's saying 50 it should say the 50. If it's saying 30 it should say a 30. That that have to move with whatever Rules there is in the standard for that employee.

# Speaker B
# Yes, we can define the, the columns first. We need to define all the required columns properly because for the 42 hours, it can be like 42 hours percentage, stuff like that. But we need to see how we can define calls properly. You can check. I will share that.

# Speaker A
# Yeah. Okay, so this is the two main things that's missing from the system right now that we need to. And also you need to make sure that it's getting the minutes from the right place because we have. Can you still see my screen? So we have. I think it's on the period, am I right? Just because I don't have information. Isn't it here it will say for this employee. Yeah, sure. The, the, I think it's under period where they, where you can follow them. How much chicken and check out and flex they have in overtime in this. Yeah. So. Yeah, no, this is not what I mean. Try to go to flex and overtime. Go a little bit down. Can you, can you go up so I can see what the numbers stand for? Over. So here it's saying undertime, overtime and approved. So for example here, if you had any overtime here, then it, it has to take from the, from when you, when you have the whole period from, from that employee, there should be some totals saying that this is how many hours you worked that week, this is how many flex you have, this is how many overtime for this percentage. This is how many overtime for this percentage. And this is how many sick days you had this, how many vacation days you had. This is how many days you worked night or weekends or evenings or holidays or anything like this, there should be some total somewhere. Do we have this? Okay, so because the numbers are supposed to come from that column because it's supposed to calculate the minutes from when you were actually from, from the actual number. So if it's saying your total overtime hours this month were 10, then the hours is 10. But then it have to make, it have to make a calculation to turn it into minutes. And these minutes are the minutes that's supposed to appear on the report.

# Speaker B
# Yeah.

# Speaker A
# So I think these totals are missing. So we need to fix this too. So I don't really know if. Can you check in the report, but where, where the numbers are actually coming from or is it just hard coded into the report? These minutes that's appearing.

# Speaker B
# You mean in this report or.

# Speaker A
# No, the XN report. Where does it, where does it get 60 from and 360? This, this is kind of interesting. It's not supposed to do it in the report. It's supposed to do it from the totals that's coming somewhere.

# Speaker B
# Okay, I will validate that. Let me check. I will check the data of periods and flex over time here and database.

# Speaker A
# Yeah. So the only thing that's not supposed to appear in the report is flex hours. So even if it's giving a total on how many flex hours you have, plus or minus, it's not moving to the report. It's just good information to have for the employee in the. In the website. But for the report, we don't have flex because you don't pay out flex. You pay out overtime only.

# Speaker B
# I will check if flex hours are included in this report will remove. If not, then.

# Speaker A
# Yeah, exactly. I will. When After. When you send me this, I will just find all the fields that needs to be here and what they're called so you can fill it out. Okay, that's it. How is it going with the D1 hardening?

# Speaker B
# I. I am done with the implementation. Going to test it right after the meeting.

# Speaker A
# Okay. Okay, that's good. Thank you.
# """

# agent, merge_prompts = build_ai_agent(api_key="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", model="gpt-4o-mini")
# output = agent.invoke(
#     {
#         'text': text,
#         "want_prompt": True,
#         "want_summary": True,
#     }
# )

# print(f"\nCLASSIFICATION_OUTPUT:- {output['classified_meeting']}\n")
# print(f"GENERATED_SUMMARY:- {output['generated_summary']}\n")

# print("=" * 60)
# print("GENERATED_SEPARATED_PROMPTS:-")
# print("=" * 60)
# for i, item in enumerate(output['generated_prompt'], 1):
#     print(f"\n[{i}] TYPE: {item['type']}")
#     print(f"    TITLE: {item['title']}")
#     print(f"    DESCRIPTION:\n    {item['description']}\n")
#     print(f"    PROMPT:\n    {item['prompt']}")
#     print("-" * 60)

# merged = merge_prompts(output['generated_prompt'])

# print("\n" + "=" * 60)
# print("GENERATED_MERGED_PROMPTS:-")
# print("=" * 60)
# for i, item in enumerate(merged, 1):
#     print(f"\n[{i}] TYPE: {item['type']}")
#     print(f"    TITLE: {item['title']}")
#     print(f"    DESCRIPTION:\n    {item['description']}\n")
#     print(f"    PROMPT:\n    {item['prompt']}")
#     print("-" * 60)
