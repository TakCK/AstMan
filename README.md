# AstMan

사내 IT 자산과 소프트웨어 라이선스를 통합 관리할 수 있는 오픈소스 웹 애플리케이션입니다.

## 1) 프로젝트명
- AstMan

## 2) 한 줄 소개
- 하드웨어 자산, 소프트웨어 라이선스, 사용자 연동(LDAP), 운영 리포트를 한곳에서 관리하는 ITAM 도구

## 3) 주요 기능
- 하드웨어 자산 관리: 등록, 조회, 수정, 상태 전환, 폐기 관리
- 소프트웨어 라이선스 관리: 보유 수량/할당/만료 관리
- LDAP 사용자 연동: 검색, 반영, 동기화 스케줄
- 일반 라이선스/구독 보고서 다운로드
- 하드웨어/소프트웨어 CSV 업로드

## 4) 화면 설명
- 대시보드: 자산/소프트웨어 현황 요약, 비용 현황 및 추이
- 하드웨어: 자산 목록, 등록, CSV 업로드, 폐기완료 관리
- 소프트웨어: 라이선스 목록, 할당 관리, 등록/수정, CSV 업로드
- 설정: 하드웨어/소프트웨어 설정, 사용자/관리자, LDAP, 메일, 브랜딩

## 5) 기술 스택
- Backend: FastAPI, SQLAlchemy
- Database: PostgreSQL
- Frontend: Vanilla JavaScript, HTML, CSS
- Deployment: Docker Compose

## 6) 빠른 시작
### 1. 환경 파일 준비
```powershell
Copy-Item .env.example .env
```

### 2. 컨테이너 실행
```bash
docker compose up -d --build
```

### 3. 접속
- Web: [http://localhost:8000/](http://localhost:8000/)
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## 7) 환경 변수 안내
`.env.example` 기준으로 최소 아래 항목을 확인하세요.

- `SECRET_KEY`: JWT/암호화 관련 키 (운영 시 반드시 변경)
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`: 초기 관리자 계정
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: DB 접속 정보
- `LDAP_BIND_PASSWORD_KEY`: LDAP Bind 비밀번호 암호화 저장용 키

## 8) 운영 시 주의사항
- 운영 환경에서는 기본 관리자 비밀번호(`ADMIN_PASSWORD`)를 즉시 변경하세요.
- `SECRET_KEY`는 충분히 긴 랜덤 문자열을 사용하세요.
- 실제 LDAP/SMTP/도메인 정보는 샘플값 대신 운영값으로 분리 관리하세요.
- 공개 저장소에는 실운영 계정/비밀번호/도메인 정보를 커밋하지 마세요.

## 9) 로드맵
- 대시보드 비용 현황 고도화(필터/정렬/시각화 확장)
- 리포트 포맷 다양화(CSV/추가 템플릿)
- 운영 편의 기능(권한/감사 로그/알림) 개선

## 10) License
- MIT License
- 자세한 내용은 [LICENSE](./LICENSE) 파일을 확인하세요.

## 11) Author
- Created by TakCK
