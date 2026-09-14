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

## Live Activity 종료와 화면 제거
- wrapper 사용 여부와 관계없이 자신이 시작하거나 인계받은 Live Activity를 종료할 때는 동일한 stream_key와 content_state.type으로 end_live_activity_stream을 한 번 호출한다. 다른 작업의 알림을 목록 순서나 최근 항목으로 추정해 종료하지 않는다.
- 종료 요청에는 content_state를 생략하지 않는다. title/subtitle에 실제 완료·실패·중단 상태를 표시하고 auto_dismiss_minutes=0을 포함해 잠금화면에서 즉시 제거를 요청한다. 작업 중 문구와 진행률을 그대로 남기지 않는다.
- progress의 percentage=100은 목표 완료가 검증됐을 때만 사용한다. 실패·중단 시에는 마지막으로 확인한 진행률(알 수 없으면 0)을 사용하고, 실패·중단 사실을 명시한다. wrapper의 명령 종료는 사용자 목표 달성 검증과 구분한다.
- 종료 요청 성공은 기기 화면에서 제거됐다는 증거가 아니다. 종료된 카드가 남더라도 같은 stream을 다시 만들거나 종료를 반복하지 말고, 전송 기록과 기기 표시를 구분해 확인한다. 앱 내부 기록 삭제를 의미하지도 않는다.

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
- 기존 지침·ActivitySmith MCP·외부 watchdog의 역할을 유지한다. watchdog은 아래 공통 실행 상태에 기록한 MCP 결과만 확인한다. 다른 클라이언트의 호출을 자동 감지한다고 설명하지 않는다.
- 실행 환경에서 hook과 동일한 정확한 thread-id 및 turn-id를 제공하는 경우에만 watchsmith_delivery.py claim을 사용해 상세 완료 알림의 전송권을 얻는다. thread ID만으로 turn을 추정하거나 로그의 최근 항목을 임의로 선택하지 않는다.
- claim 결과가 send일 때만 기존 ActivitySmith MCP로 전송한다. 반환된 correlation_tag만 tags에 추가하고, 원본 Codex ID는 보내지 않는다. wait/skip이면 상세 결과를 로컬에 보관한다.
- 명시적 MCP 성공 응답 후 같은 ID와 token으로 finish --outcome accepted를 기록한다. 전송 결과가 불명확하면 unknown으로 기록하고 무작정 재전송하지 않는다. 이 조율은 사용자 동의를 대체하지 않는다.
- turn ID가 제공되지 않으면 자동 상세/일반 중복 제거를 보장하지 않는다. 일반 hook은 유지하고, 동의한 상세 공유를 수행했다면 별도 hook 알림이 올 수 있음을 구분한다.
- 같은 설치의 일반 notifier는 전송 기록을 공유한다. 다른 사용자 notifier·MCP 클라이언트의 독립 전송까지 제거된다고 주장하지 않는다.

## wrapper 안의 진행 알림 조율
- WATCHSMITH_PROGRESS_CONTEXT와 WATCHSMITH_PROGRESS_HELPER가 제공되면 python3 "$WATCHSMITH_PROGRESS_HELPER" claim을 Live Activity 시작/업데이트 전에 실행한다. 이 환경은 codex-watch가 감싼 단일 프로세스 실행 범위이며 turn ID가 아니다.
- send일 때만 반환된 stream_key로 기존 set_live_activity_stream을 호출한다. content_state.type은 progress로 고정하고 같은 키를 유지한다. 작업명/단계는 title/subtitle, 진행률을 알 때만 percentage에 담는다. 대상 채널은 기본값을 유지한다.
- MCP 호출 직후 python3 "$WATCHSMITH_PROGRESS_HELPER" finish --token <반환 token> --outcome accepted를 명시적 성공에만 기록한다. 실패는 failed, 불명확한 응답은 unknown으로 기록한다. claim은 90초 유효하므로 호출 직전에 얻고, 전송 전에 만료됐다면 다시 claim한다. 동일 상태를 위한 원격 heartbeat는 보내지 않는다.
- wait이면 진행 알림을 중복 시작하지 않는다. 다음 의미 있는 단계에서 다시 claim할 수 있다. skip이면 종료된 실행이므로 새로 보내지 않는다. 환경이 없거나 helper가 unavailable/오류를 반환하면 연결됐다고 가정하지 않고 기존 MCP 지침을 따른다.
- 성공 등록된 진행 알림은 해당 프로세스가 끝날 때까지 watchdog fallback을 억제한다. watchdog이 먼저 시작했어도 같은 stream_key/type으로 의미 있는 단계부터 이어받는다. wrapper는 프로세스 종료 때 남은 stream을 CLI로 한 번 종료 시도한다.
- 에이전트가 먼저 종료할 때는 기존 MCP end_live_activity_stream을 한 번 호출하고, 명시적 성공 후 python3 "$WATCHSMITH_PROGRESS_HELPER" ended를 기록한다. 이를 통해 wrapper의 중복 종료를 막는다. CLI에 end-stream이 없는 환경에서는 이 MCP 종료가 필요하다.
- 이 실행 식별자를 완료 알림의 thread/turn ID 대신 사용하지 않는다. Desktop 및 interactive session의 turn별 연결을 보장하지 않는다.

<!-- END codex-watchsmith activitysmith workflow -->
