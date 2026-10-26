# 사용자가 연 쇼피 페이지 기록 도구

이 도구는 Chrome에서 **현재 열려 있는 페이지**의 화면에 렌더링된 정샘물 상품 링크와 표시값을 기록합니다. 자동 로그인, 페이지 이동, 숨은 API 호출, CAPTCHA 해결, 지역 우회, 외부 서버 전송 기능은 없습니다. 검색 결과가 오류라면 `page_error`와 0건을 남깁니다. Chrome 확장 기능 자체는 사용자 Windows Chrome에서 아직 시험하지 않았고, 저장된 실제 상품 카드로 추출 로직을 검증했습니다.

## 한 번만 설치

1. 이 저장소를 ZIP으로 내려받아 압축 해제하거나 로컬 체크아웃을 사용합니다.
2. Chrome 주소창에서 `chrome://extensions`를 열고 개발자 모드를 켭니다.
3. `압축해제된 확장 프로그램을 로드합니다`에서 이 `browser_capture` 폴더를 선택합니다.

## 사용

1. 평소 사용하는 Chrome에서 쇼피 검색 결과 페이지를 정상적으로 엽니다. 로그인은 직접 진행합니다.
2. 화면에 원하는 상품 카드가 보이면 확장 아이콘을 한 번 클릭합니다. 다운로드 폴더의 `Shopee_TW_Captures/capture_*.json`에 페이지 URL·관측 시각·상품/상점 ID·표시 가격·표시 판매량이 저장됩니다. 배지 숫자는 기록된 상품 수, `ERR`는 오류입니다.
3. 추가 페이지가 정상적으로 열릴 때마다 같은 동작을 반복합니다. 페이지가 열리지 않으면 오류 상태도 파일로 남습니다. 페이지 전체나 해당 상점의 모든 상품을 수집했다는 뜻으로 해석하지 않습니다.

결과 폴더에서 저장소 루트의 명령을 실행하면 기존 TRACK B 스키마로 변환됩니다.

```powershell
py shopee_tw/track_b/import_observations.py --capture-dir "$HOME/Downloads/Shopee_TW_Captures" --out shopee_tw/output/track_b_local
```

결과는 `observations.csv`, `deduped_listings.csv`, `seller_master.csv`, `coverage_report.json`입니다. GitHub Actions는 코드·기존 증거의 처리 재현성을 검증하며, 사용자의 로그인 브라우저를 원격 실행하지 않습니다. 계정 정보·쿠키는 저장하지 않습니다. 사용자가 사이트에서 볼 수 있는 페이지와 해당 사이트의 이용 조건 안에서만 사용해야 합니다.
