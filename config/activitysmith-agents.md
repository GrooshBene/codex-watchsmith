<!-- BEGIN codex-watchsmith activitysmith workflow -->
# ActivitySmith 자율 작업 상태 알림
- 프로젝트 종류와 관계없이 사용할 수 있다.
- 약 1분 이상 걸릴 가능성이 있거나 여러 단계/tool call이 예상되면 ActivitySmith 사용을 우선한다.
- 실제 1분이 지난 뒤가 아니라 계획 단계에서 선제적으로 Live Activity 시작을 고려한다.
- 처음엔 짧다고 판단했더라도 1분을 넘기거나 단계가 증가하면 즉시 재평가한다.
- 완료/실패/blocker/사용자 판단 필요 시 Push를 보낸다.
- 의미 있는 단계 변화에만 Live Activity를 업데이트한다.
- API key, token, password, 개인정보, 고객 데이터, 소스코드 전문, 회사 기밀, 내부 URL/IP, 원본 문서·음원, 프롬프트 전문은 ActivitySmith로 보내지 않는다.
- 애매하면 사용자가 다른 앱을 보거나 자리를 비웠다가 모바일 알림을 받고 돌아오는 것이 유용한지를 기준으로 판단하고, 그렇다면 사용한다.
<!-- END codex-watchsmith activitysmith workflow -->
