import asyncio
import json
import logging
import os
from copy import deepcopy
from datetime import date
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from agent_framework.exceptions import AgentException

try:
    from agent_framework.orchestrations import SequentialBuilder
except ImportError:
    SequentialBuilder = None

from agent_framework_github_copilot import GitHubCopilotAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Reply Desk")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ORDERS: dict[str, dict[str, Any]] = {
    f"ORD-{1000 + number}": {
        "order_number": f"ORD-{1000 + number}",
        "customer_name": f"샘플 고객 {number}",
        "contact": f"010-0000-{1000 + number:04d}",
        "product_name": product,
        "amount": amount,
        "order_date": f"2026-{(number % 9) + 1:02d}-{(number % 26) + 1:02d}",
        "shipping_status": shipping_status,
        "refund_status": "없음",
    }
    for number, product, amount, shipping_status in [
        (1, "무선 키보드", 59000, "배송완료"),
        (2, "텀블러", 24000, "배송중"),
        (3, "노트북 거치대", 42000, "배송준비"),
        (4, "블루투스 이어폰", 89000, "배송완료"),
        (5, "데스크 매트", 18000, "배송중"),
        (6, "USB 허브", 32000, "배송완료"),
        (7, "모니터 조명", 47000, "배송준비"),
        (8, "스마트폰 케이스", 22000, "배송완료"),
        (9, "노트 세트", 12000, "배송중"),
        (10, "미니 가습기", 36000, "배송준비"),
        (11, "웹캠", 67000, "배송완료"),
        (12, "마우스", 39000, "배송중"),
        (13, "충전 케이블", 15000, "배송완료"),
        (14, "서류 가방", 73000, "배송준비"),
        (15, "책상 선반", 51000, "배송중"),
        (16, "노트북 파우치", 28000, "배송완료"),
        (17, "키보드 팜레스트", 27000, "배송준비"),
        (18, "스피커", 64000, "배송중"),
        (19, "캔들 워머", 33000, "배송완료"),
        (20, "여행용 어댑터", 29000, "배송준비"),
    ]
}
INITIAL_ORDERS = deepcopy(ORDERS)
INQUIRIES: list[dict[str, Any]] = []


def order_for_prompt(order: dict[str, Any]) -> str:
    return json.dumps(order, ensure_ascii=False)


def response_text(result: Any) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    messages = getattr(result, "messages", None)
    if messages:
        return str(messages[-1])
    return str(result)


async def run_pipeline(inquiry: str, order: dict[str, Any]) -> str:
    async with GitHubCopilotAgent(
        instructions=(
            "문의 유형을 배송, 환불, 교환, 기타 중 하나로 분류하고 불만도를 1에서 5 사이 "
            "정수로 판단하세요. 다음 답변 에이전트가 사용할 수 있도록 분류 결과를 명확히 "
            "작성하세요. 분류 결과만 간결하게 작성하세요."
        ),
    ) as classifier, GitHubCopilotAgent(
        instructions=(
            "앞선 분류 결과와 주문 정보를 바탕으로 고객에게 보낼 한국어 답변을 작성하세요. "
            "반드시 마지막에 다른 텍스트 없이 다음 JSON 객체만 출력하세요: "
            '{"category": "...", "anger": 숫자, "reply": "...", "refund": true/false}. '
            "category는 배송, 환불, 교환, 기타 중 하나이고 anger는 1~5 정수입니다. "
            "환불 요청이면 refund는 true로 하세요. 답변 마지막에 JSON 객체만 출력하세요."
        ),
    ) as writer:
        if SequentialBuilder is None:
            raise RuntimeError("Sequential orchestration API is unavailable")
        workflow = SequentialBuilder(participants=[classifier, writer]).build()
        pipeline = workflow.as_agent()
        prompt = f"주문 정보: {order_for_prompt(order)}\n고객 문의: {inquiry}"
        result = await pipeline.run(prompt)
        return response_text(result)


def parse_result(raw_result: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_result)
        category = parsed["category"]
        anger = int(parsed["anger"])
        reply = str(parsed["reply"])
        refund = bool(parsed["refund"])
        if category not in {"배송", "환불", "교환", "기타"} or not 1 <= anger <= 5:
            raise ValueError("invalid result")
        return {
            "category": category,
            "anger": anger,
            "reply": reply,
            "refund": refund,
        }
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"category": "기타", "anger": None, "reply": raw_result, "refund": False}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"result": None, "error": None, "form": {}},
    )


@app.post("/inquiries", response_class=HTMLResponse)
async def create_inquiry(
    request: Request,
    customer_name: str = Form(""),
    order_number: str = Form(""),
    inquiry: str = Form(""),
) -> HTMLResponse:
    form = {
        "customer_name": customer_name,
        "order_number": order_number,
        "inquiry": inquiry,
    }
    order = ORDERS.get(order_number)
    if not order:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"result": None, "error": "주문번호를 확인해 주세요", "form": form},
            status_code=400,
        )
    try:
        raw_result = await asyncio.wait_for(run_pipeline(inquiry, order), timeout=100)
    except (asyncio.TimeoutError, RuntimeError, ConnectionError, AgentException):
        logger.exception("AI response generation failed")
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "result": None,
                "error": "답변 생성에 실패했습니다. 다시 시도해 주세요",
                "form": form,
            },
            status_code=502,
        )
    result = parse_result(raw_result)
    if result["refund"]:
        order["refund_status"] = "환불완료"
    inquiry_record = {
        "customer_name": customer_name,
        "order_number": order_number,
        "inquiry": inquiry,
        "category": result["category"],
        "anger": result["anger"],
        "reply": result["reply"],
        "refund_status": order["refund_status"],
        "created_at": date.today().isoformat(),
    }
    INQUIRIES.append(inquiry_record)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"result": inquiry_record, "error": None, "form": {}},
    )


@app.get("/inquiries", response_class=HTMLResponse)
async def inquiry_list(request: Request, refund_filter: str = "all") -> HTMLResponse:
    if refund_filter not in {"all", "환불완료", "없음"}:
        refund_filter = "all"
    inquiries = [
        item
        for item in INQUIRIES
        if refund_filter == "all" or item["refund_status"] == refund_filter
    ]
    return templates.TemplateResponse(
        request=request,
        name="list.html",
        context={"inquiries": inquiries, "refund_filter": refund_filter},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"message": None, "error": None},
    )


@app.post("/admin/reset", response_class=HTMLResponse)
async def reset_data(request: Request, password: str = Form("")) -> HTMLResponse:
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"message": None, "error": "ADMIN_PASSWORD 환경변수를 설정해 주세요"},
        )
    if password != admin_password:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"message": None, "error": "비밀번호가 올바르지 않습니다"},
            status_code=403,
        )
    ORDERS.clear()
    ORDERS.update(deepcopy(INITIAL_ORDERS))
    INQUIRIES.clear()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"message": "데이터를 초기화했습니다", "error": None},
    )
