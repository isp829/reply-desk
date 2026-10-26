# Reply Desk

쇼핑몰 고객 문의를 분류하고 답변 초안을 작성하는 웹 앱입니다.  
대상 사용자: 고객 문의를 직접 처리하는 소규모 온라인 쇼핑몰 운영자

기획서: [PRD.md](PRD.md)

배포 링크: https://reply-desk-isp829.azurewebsites.net

## 로컬 실행

1. GitHub Copilot CLI를 설치합니다.

   ```bash
   npm install -g @github/copilot
   ```

2. `GITHUB_TOKEN`을 설정합니다. 관리자 초기화 기능을 사용하려면 `ADMIN_PASSWORD`도 설정합니다.
3. 의존성을 설치하고 서버를 실행합니다.

   ```bash
   pip install --pre -r requirements.txt
   uvicorn main:app --reload
   ```

응답까지 수십 초 걸릴 수 있습니다.

## 사용 예시

샘플 주문번호는 `ORD-1001` ~ `ORD-1020`입니다.

- 예시 1: `ORD-1003 / 배송이 언제 오나요?`
- 예시 2: `ORD-1007 / 환불해 주세요`

## 에이전트 구성

`agent-framework-github-copilot`의 `GitHubCopilotAgent` 두 개를 사용합니다. 설치된 최신 API에서는 `agent_framework.orchestrations.SequentialBuilder`로 순차 워크플로를 만들고, `as_agent()`로 실행합니다. 구형 설치에서 제공되는 `SequentialOrchestrator`도 호환 경로로 지원합니다.
