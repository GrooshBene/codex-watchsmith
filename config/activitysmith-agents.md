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

## 상황별 Live Activity 선택
- 시작 시 단계가 명확하면 segmented_progress, 실제 진행량을 알면 progress, 진행률을 모르면 경과 시간 timer를 사용한다. stats/metrics는 실제 측정값이 있을 때만 사용하며, alert는 현재 상태 안내에 사용한다. 타입을 다양하게 보이게 하려고 임의의 수치·시간·단계를 만들지 않는다.
- 동일 실행에서는 먼저 선택된 타입을 유지한다. 상태 변화는 title/subtitle·색상·아이콘·지원되는 배지로 표현한다. 기본 색상은 진행 blue, 판단 대기 orange, 실패 red, 완료 green이다. 색상만으로 상태를 전달하지 않는다.
- 사용자 판단이 필요하면 아래 원격 확인 규칙과 ActivitySmith 전용 승인 도구를 사용한다. 앱 종료 후 자동 재개나 Codex 자체 권한 승인을 대신한다고 설명하지 않는다.
- 완료 시 새 Live Activity를 만들지 않고 기존 카드를 종료한다. 사용자에게 허용받은 경우 작업명과 결과 요약 Push를 보낸다. 일반 완료 hook과의 중복 조율은 기존 정확한 ID 조건을 유지한다.

## 상황별 메시지 선택
- 계획·분석·구현·검증·빌드·설치·배포·재시도·복구 등 실제 단계가 바뀌면 작업명과 현재 수행 내용을 갱신한다. 사용자가 허용한 작업을 진행하기 위해 불필요한 확인 질문을 추가하지 않는다. 같은 상태를 반복 전송하는 heartbeat는 보내지 않는다.
- 설치된 watchsmith_result.py --list-scenarios로 29개 상황을 확인한다. 검토한 JSON을 watchsmith_result.py <파일> --scenario <상황> --share-preview로 처리하면 기존 MCP 도구에 전달할 인수와 전달 경로를 반환한다. 이 helper는 전송·명령 실행·응답 대기를 수행하지 않는다. 명령·대상에도 비밀이나 개인정보가 있으면 외부 승인에 담지 말고 로컬 확인을 사용한다.
- 입력의 task_name은 작업명, summary는 실제 수행 내용·판단 근거다. “작업 중”만 쓰지 말고 지금 무엇을 확인하거나 변경하는지 간결하게 적는다. 문구를 다양하게 만들기 위해 사실이나 진행률을 만들지 않는다.
- 단계형은 실제 current_step/number_of_steps, 진행률형은 실제 percentage를 제공한다. 측정값이 없으면 기본 시간형을 사용한다. metrics/stats는 실제 수치가 있을 때만 사용한다.
- route=live_activity이면 동일 작업의 stream_key와 타입을 유지한다. 카드가 이미 있다면 activity_type과 해당 타입의 실제 수치·timer_start_at을 이어받는다. wrapper 환경에서는 기존 claim 절차를 먼저 거치고, helper의 제안보다 claim이 반환한 키·타입·내용을 우선한다. 동일 실행의 타이머 시작 시각을 초기화하지 않는다.
- route=completion_hook이면 최종 답변에 작업명·결과·검증·남은 문제를 표현하고 자동 완료 hook에 맡긴다. completed/partial/failed/cancelled/expired는 실제 상태로 선택한다. 시나리오 출력을 추가 MCP 완료 Push로 보내지 않는다.

## 원격 확인과 후속 작업
- 아직 허용받지 않은 구체적인 후속 작업에서만 질문한다. approve_validation/approve_commit/approve_push/approve_release/approve_retry/approve_alternative/approve_resume 중 맞는 상황을 선택한다. 이미 받은 커밋·푸시 등의 지속적인 허용은 유지한다.
- 요청 전 수행할 정확한 명령 또는 도구 인수, 대상 범위와 변경 내용을 확정하고 검토한다. execution_context와 scope를 포함한다. 사용자가 선택할 대상이 구체적이지 않으면 승인 요청을 만들지 않는다.
- 반환된 request_approval 인수를 사용한다. 실제 클라이언트의 MCP Tasks 지원과 결과 회수가 확인된 경우에만 request_approval_task를 선택한다. 버튼은 “커밋 진행 / 여기서 종료”, “재시도 / 중단”처럼 두 행동을 명확히 표시한다. 세 선택지가 필요하면 별도 후속 질문으로 나눈다.
- 선택 알림은 기본 delivery=live_activity로 보내 버튼을 바로 보여준다. 실제 delivery_surface를 확인하고 도구 성공만으로 기기 표시를 단정하지 않는다. Push는 사용자가 요청하거나 Live Activity를 사용할 수 없다고 확인된 경우의 보조 수단이다. Push 또는 auto를 선택하면 “Push 알림은 길게 눌러 선택하세요” 안내를 포함한다. 명령 승인 Push의 제목이 서버에서 Approve command로 표시될 수 있으므로 질문 전체가 제목이라고 안내하지 않는다.
- wrapper 밖에서는 자신이 소유한 진행 카드만 종료한 뒤 승인 카드를 요청한다. wrapper 안에서는 python3 "$WATCHSMITH_PROGRESS_HELPER" approval-pause를 먼저 호출한다. send일 때 반환된 pause_live_activity_stream 인수를 사용하고, 같은 token으로 approval-finish --outcome accepted/failed/unknown을 기록한다. 명시적 원격 성공과 recorded=true 또는 ready 응답을 확인한 뒤에만 승인 카드를 요청한다. wait/skip이면 새 카드를 만들지 않는다. pause는 선택 대기를 위한 실제 중단이며 ended로 실행 전체를 닫지 않는다.
- 승인 후 후속 작업을 계속할 때 wrapper의 approval-resume으로 받은 resume_live_activity_stream 인수를 사용하고 approval-finish로 성공을 기록한다. 그 뒤 기존 claim/set/finish 절차로 같은 키·타입·시작 시각을 이어받는다. 거절·취소·만료 뒤 작업을 마치면 진행 표시를 재개하지 않는다. 남은 자신의 스트림은 기존 종료 규칙으로 정리한다.
- 전환 결과가 unknown이거나 프로세스가 끊겼으면 pause/resume이 성공했다고 추정하지 않는다. 로컬 전환 상태는 진행 claim과 watchdog을 계속 억제한다. 다른 키로 우회하거나 승인 요청을 반복하지 말고 원격 상태를 확인한다. 복구를 확정할 수 없으면 실행을 중단하고 자신의 스트림을 정리한다. 종료된 실행은 늦은 확인 응답으로 다시 열지 않는다.
- 질문을 한 번 만든 후 반환된 approval ID를 유지한다. pending이면 같은 ID로 wait_for_approval을 사용하고, 대기 호출 종료를 승인 요청 만료나 거절로 해석하지 않는다. pending마다 새 질문·Push를 생성하지 않는다. 대기 중 최종 응답을 보내 작업을 완료 처리하지 않는다.
- 서버가 해당 요청의 승인 상태를 명시적으로 반환했을 때만, 현재 대화에서 아직 실행하지 않은 동일한 범위의 후속 작업을 한 번 수행한다. 실행 직전에 대상·변경 내용이 승인 시점과 같고 요청이 취소되지 않았는지 확인한다. 범위가 달라지면 기존 승인을 재사용하지 않는다. 결과가 불명확한 실행을 자동 재시도하지 않는다.
- 거절·취소·만료이면 후속 작업을 실행하지 않고 실제 중단 사유로 마무리한다. 로컬에서 사용자가 취소하거나 요청이 더 이상 필요 없으면 같은 approval ID로 cancel_approval을 호출한다. 서버 응답이 불명확하면 get_approval로 확인하며 승인으로 추정하지 않는다.
- 승인 질문 자체에 현재 결과가 포함되면 같은 순간에 완료 요약 Push를 따로 보내지 않는다. 선택 뒤 후속 작업을 진행하거나 중단한 최종 결과는 기존 완료 hook이 전송한다.
- 이 흐름은 활성 에이전트 세션 안의 작업 진행 규칙이다. 프로세스 종료·앱 재시작 후 자동 복구, 영구적인 한 번만 실행 보장, Codex의 샌드박스/도구 권한 승인 우회는 제공하지 않는다. 세션이 끊겼다면 상태와 실행 여부를 다시 확인하기 전에는 이어서 실행하지 않는다.

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
- 작업명·결과를 잠금화면에 표시하도록 사용자가 동의했다면 task_name(60자 이내), notification_summary(180자 이내)를 별도로 검토해 작성하고 watchsmith_result.py --share-preview를 사용한다. 이 동의는 metadata 상세 공유와 별개다. 전체 응답을 잘라 쓰지 않으며, 실패·부분 완료·확인 필요를 완료로 표시하지 않는다. 이 도구는 전송하지 않고 기존 MCP 인수만 만든다.
- 설치된 watchsmith_result.py는 결과 JSON을 로컬에서 검증하고 MCP 인수 JSON만 출력한다. --share-details는 검토·동의한 요약을 포함하며 --include-result-link는 검토한 링크를 추가한다. 이 플래그는 비밀 정보 자동 탐지나 전송 기능이 아니다.
- JSON 출력은 데이터로 다루고 ActivitySmith의 기존 send_push_notification 도구 인수로 전달한다. 별도 승인 서버·알림 서버·파일 업로드를 만들지 않는다.
- 상세 결과 Push가 성공하면 같은 에이전트에서 일반 완료 Push를 추가로 보내지 않는다. notify hook이나 기존 notifier의 별도 Push까지 자동 중복 제거된다고 주장하지 않는다.
- 전송 성공과 metadata 저장 확인, 실제 기기 표시 확인을 구분한다. 메타데이터를 지원하지 않으면 상세 내용을 일반 payload나 알림 본문에 대신 넣지 않는다.
- 로컬 보고서는 저장소 밖 또는 무시되는 .codex 디렉터리에 보관한다. 링크가 없으면 파일을 임의로 업로드하지 않는다.


## 완료 요약과 일반 hook 단일 전송
- 기본 완료 Push는 hook이 현재 완료 이벤트의 사용자 요청과 마지막 답변에서 로컬로 추출해 한 번 보낸다. 같은 완료 결과를 MCP Push로 별도 전송하지 않는다. 응답이 끝났다는 사실과 사용자 목표 달성을 구분한다.
- 최종 답변 첫 문단에 작업명·실제 수행 내용·결과를 간결하게 작성한다. 실제 검증 결과와 남은 문제·미적용 범위는 명확한 문장으로 적는다. 모바일에 공유할 수 없는 정보는 요약 문장에 넣지 않는다.
- 최종 답변에 내부 참조값이나 HTML 결과 표식을 넣지 않는다. 기본 흐름에는 결과 파일이나 사전 큐 등록이 필요 없다. 이전 지침이 남아 있어도 결과 표식을 만들거나 복사하지 않는다.
- 선택적으로 검토한 preview를 지정하려면 watchsmith_result.py <파일> --share-preview --queue-for-hook에 신뢰할 수 있는 정확한 thread ID와 turn ID가 모두 있어야 한다. ID가 없으면 추측하거나 최근 로그를 뒤지지 않고 기본 자동 요약을 사용한다. 큐 누락·만료·불일치도 현재 완료 이벤트 자동 요약으로 처리한다.
- 자동 추출은 별도 모델 호출 없이 수행되며 전체 대화·파일을 읽거나 업로드하지 않는다. WATCHSMITH_COMPLETION_PREVIEW=0인 notifier 환경은 내용 없는 일반 응답 종료 알림만 보낸다. 알려진 민감 정보 형태를 제외하는 처리는 모든 개인정보나 기밀의 탐지를 보장하지 않는다.
- metadata 상세 전송이 필요한 경우 기존 MCP 경로와 별도의 공유 동의를 유지한다. 같은 hook의 정확한 thread-id와 turn-id가 있을 때만 watchsmith_delivery.py claim으로 조율한다. send일 때만 전송하고 반환 correlation_tag만 tags에 추가한다. wait/skip이면 전송하지 않는다.
- 직접 MCP 전송의 명시적 성공은 finish --outcome accepted, 불명확한 결과는 unknown으로 기록한다. unknown은 중복 위험 때문에 자동 재전송하지 않는다. 기존 Computer Use/사용자 notify 연결을 보존한다. ID 누락·저장소 오류·독립 외부 notifier의 중복 및 실제 기기 표시까지 보장하지 않는다.

## wrapper 안의 진행 알림 조율
- WATCHSMITH_PROGRESS_CONTEXT와 WATCHSMITH_PROGRESS_HELPER가 제공되면 python3 "$WATCHSMITH_PROGRESS_HELPER" claim을 Live Activity 시작/업데이트 전에 실행한다. 이 환경은 codex-watch가 감싼 단일 프로세스 실행 범위이며 turn ID가 아니다.
- send일 때만 반환된 stream_key로 기존 set_live_activity_stream을 호출한다. 반환된 content_state_type과 content_state를 사용하고 같은 키를 유지한다. 처음 타입을 제안하거나 같은 타입의 표시값을 갱신할 때 claim --content-state로 검토한 JSON을 전달한다. type_locked=true이면 새로 제안한 타입을 버리고 반환된 타입과 필수 필드를 이어받는다. watchdog이 먼저 시작한 신규 실행은 경과 시간 timer이며, 기존 컨텍스트의 progress는 유지한다. 작업명/단계는 title/subtitle, 진행률을 알 때만 percentage에 담는다. 대상 채널은 기본값을 유지한다.
- MCP 호출 직후 python3 "$WATCHSMITH_PROGRESS_HELPER" finish --token <반환 token> --outcome accepted를 명시적 성공에만 기록한다. 실패는 failed, 불명확한 응답은 unknown으로 기록한다. claim은 90초 유효하므로 호출 직전에 얻고, 전송 전에 만료됐다면 다시 claim한다. 동일 상태를 위한 원격 heartbeat는 보내지 않는다.
- wait이면 진행 알림을 중복 시작하지 않는다. 다음 의미 있는 단계에서 다시 claim할 수 있다. skip이면 종료된 실행이므로 새로 보내지 않는다. 환경이 없거나 helper가 unavailable/오류를 반환하면 연결됐다고 가정하지 않고 기존 MCP 지침을 따른다.
- 성공 등록된 진행 알림은 해당 프로세스가 끝날 때까지 watchdog fallback을 억제한다. watchdog이 먼저 시작했어도 같은 stream_key/type으로 의미 있는 단계부터 이어받는다. wrapper는 프로세스 종료 때 남은 stream을 CLI로 한 번 종료 시도한다.
- 에이전트가 먼저 종료할 때는 기존 MCP end_live_activity_stream을 한 번 호출하고, 명시적 성공 후 python3 "$WATCHSMITH_PROGRESS_HELPER" ended를 기록한다. 이를 통해 wrapper의 중복 종료를 막는다. CLI에 end-stream이 없는 환경에서는 이 MCP 종료가 필요하다.
- 이 실행 식별자를 완료 알림의 thread/turn ID 대신 사용하지 않는다. Desktop 및 interactive session의 turn별 연결을 보장하지 않는다.

<!-- END codex-watchsmith activitysmith workflow -->
