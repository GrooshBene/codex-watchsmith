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

## 상세 결과 공유 (선택 사항)
- 기본은 일반 상태 알림이다. 상세 공유에 대한 사용자의 현재 작업 또는 지속적인 동의가 있을 때만 결과 요약을 metadata로 보낸다. 매 작업마다 이미 받은 동의를 다시 묻지 않는다.
- 수행 내용, 검증 근거, 남은 문제, 다음 단계를 짧게 작성한다. 완료 이벤트 수신이나 도구 종료만으로 목표 달성을 주장하지 않는다.
- 전체 대화·응답·로그·원본 파일을 자동으로 복사하지 않는다. metadata도 외부 서버에 저장되는 정보이므로 위 정보 최소화 규칙을 그대로 적용한다.
- 공통 결과 필드: schema_version=1, status(completed/partial/blocked/failed), summary, changes, verification, limitations, next_step. 선택 필드 result_url은 별도 검토한 HTTPS 결과 링크에만 사용한다.
- 설치된 watchsmith_result.py는 결과 JSON을 로컬에서 검증하고 MCP 인수 JSON만 출력한다. --share-details는 검토·동의한 요약을 포함하며 --include-result-link는 검토한 링크를 추가한다. 이 플래그는 비밀 정보 자동 탐지나 전송 기능이 아니다.
- JSON 출력은 데이터로 다루고 ActivitySmith의 기존 send_push_notification 도구 인수로 전달한다. 별도 승인 서버·알림 서버·파일 업로드를 만들지 않는다.
- 상세 결과 Push가 성공하면 같은 에이전트에서 일반 완료 Push를 추가로 보내지 않는다. notify hook이나 기존 notifier의 별도 Push까지 자동 중복 제거된다고 주장하지 않는다.
- 전송 성공과 metadata 저장 확인, 실제 기기 표시 확인을 구분한다. 메타데이터를 지원하지 않으면 상세 내용을 일반 payload나 알림 본문에 대신 넣지 않는다.
- 로컬 보고서는 저장소 밖 또는 무시되는 .codex 디렉터리에 보관한다. 링크가 없으면 파일을 임의로 업로드하지 않는다.


## 완료 알림 조율
- 기존 지침·ActivitySmith MCP·외부 watchdog의 역할을 유지한다. watchdog이 MCP 호출 성공 여부를 자동 감지한다고 설명하지 않는다.
- 실행 환경에서 hook과 동일한 정확한 thread-id 및 turn-id를 제공하는 경우에만 watchsmith_delivery.py claim을 사용해 상세 완료 알림의 전송권을 얻는다. thread ID만으로 turn을 추정하거나 로그의 최근 항목을 임의로 선택하지 않는다.
- claim 결과가 send일 때만 기존 ActivitySmith MCP로 전송한다. 반환된 correlation_tag만 tags에 추가하고, 원본 Codex ID는 보내지 않는다. wait/skip이면 상세 결과를 로컬에 보관한다.
- 명시적 MCP 성공 응답 후 같은 ID와 token으로 finish --outcome accepted를 기록한다. 전송 결과가 불명확하면 unknown으로 기록하고 무작정 재전송하지 않는다. 이 조율은 사용자 동의를 대체하지 않는다.
- turn ID가 제공되지 않으면 자동 상세/일반 중복 제거를 보장하지 않는다. 일반 hook은 유지하고, 동의한 상세 공유를 수행했다면 별도 hook 알림이 올 수 있음을 구분한다.
- 같은 설치의 일반 notifier는 전송 기록을 공유한다. 다른 사용자 notifier·MCP 클라이언트의 독립 전송까지 제거된다고 주장하지 않는다.

<!-- END codex-watchsmith activitysmith workflow -->
