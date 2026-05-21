# 사내망 배포 가이드

> Streamlit 대시보드를 사내 팀원에게 노출하기 위한 안전한 패턴.
> 일상 운영은 [RUNBOOK](RUNBOOK.md) 참조.

---

## ⚠️ 외부 공개 금지

| 리스크 | 영향 |
|---|---|
| **저작권** | 제조사·다나와·쿠팡 이미지/스펙/리뷰가 외부 노출되면 저작권 침해 가능 |
| **API 비용** | 외부 접근 시 LLM 호출 폭증으로 Anthropic 비용 폭주 |
| **rate limit** | 외부 IP로 다나와/쿠팡 호출 시 사내 IP 차단 위험 |

**원 plan의 명시 사항**: "외부 노출 차단: Streamlit 서버 사내망 한정 (README 명시)"

---

## 패턴 A: SSH 터널 (default, 권장)

본인 + 신뢰 팀원 1~5명에게 적합. 추가 인프라 0.

### A.1 서버 측
```bash
source .venv/bin/activate

# 127.0.0.1로 명시 바인딩 (0.0.0.0 절대 금지)
streamlit run src/lg_dash/app/dashboard.py \
  --server.address 127.0.0.1 \
  --server.port 8501
```

### A.2 클라이언트 측 (팀원 PC)
```bash
ssh -L 8501:127.0.0.1:8501 user@lg-dash-host
# 새 터미널에서 그대로 유지

# 브라우저
open http://localhost:8501
```

### A.3 백그라운드 실행 (서버에 SSH 로그아웃해도 유지)
```bash
# nohup
nohup streamlit run src/lg_dash/app/dashboard.py \
  --server.address 127.0.0.1 > storage/streamlit.log 2>&1 &
echo $! > storage/streamlit.pid

# 종료
kill $(cat storage/streamlit.pid) && rm storage/streamlit.pid

# 또는 systemd user service (재기동 자동복구)
```

### A.4 systemd user service (선택)
`~/.config/systemd/user/lg-dash.service`:
```ini
[Unit]
Description=lg_dash Streamlit dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/lg_dash/workspace
ExecStart=/opt/lg_dash/workspace/.venv/bin/streamlit run \
  src/lg_dash/app/dashboard.py \
  --server.address 127.0.0.1 --server.port 8501
Restart=on-failure

[Install]
WantedBy=default.target
```
```bash
systemctl --user enable --now lg-dash.service
systemctl --user status lg-dash.service
```

### A.5 장단점
| 장점 | 단점 |
|---|---|
| 인프라 0 (Streamlit + SSH만) | 사용자별 SSH 권한 필요 |
| 외부 노출 0 (127.0.0.1) | 5+ 사용자 시 SSH 키 관리 비용 |
| 추가 비용 0 | SSH 터널 끊기면 재연결 필요 |

---

## 패턴 B: nginx reverse proxy + IP allowlist + basic auth (옵션)

사내 동일 서브넷 5+ 사용자 또는 SSH 권한 부여가 부담스러운 환경.

### B.1 전제
- 서버에 nginx 설치 (`apt install nginx` 등)
- 사내 IP 범위 명확 (예: `10.0.0.0/8`, `192.168.0.0/16`)
- DNS `lg-dash.internal`이 사내에서만 resolve (또는 hosts 파일)

### B.2 nginx config 예시
`/etc/nginx/sites-available/lg-dash`:
```nginx
server {
    listen 80;
    server_name lg-dash.internal;

    # 사내 IP만 허용 (필수)
    allow 10.0.0.0/8;
    allow 192.168.0.0/16;
    deny all;

    # basic auth (필수)
    auth_basic "lg_dash internal";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Streamlit WebSocket
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

```bash
# htpasswd 파일 생성 (apache2-utils 또는 nginx-extras)
sudo htpasswd -c /etc/nginx/.htpasswd teamuser1
sudo htpasswd /etc/nginx/.htpasswd teamuser2   # 추가는 -c 없이

# 활성화 + reload
sudo ln -s /etc/nginx/sites-available/lg-dash /etc/nginx/sites-enabled/
sudo nginx -t   # syntax check
sudo systemctl reload nginx
```

### B.3 Streamlit 측
```bash
# nginx가 :80 → :8501 프록시. Streamlit은 여전히 127.0.0.1.
streamlit run src/lg_dash/app/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

### B.4 검증
- 사내 IP에서 `http://lg-dash.internal` → basic auth prompt → 대시보드
- 사외 IP에서 `http://lg-dash.internal` → 403 Forbidden (allow/deny 동작)
- (선택) HTTPS는 사내 CA 또는 self-signed로 추가 가능

---

## ❌ 안티패턴 (절대 금지)

| 패턴 | 왜 금지 |
|---|---|
| `streamlit run --server.address 0.0.0.0` | 모든 인터페이스 바인딩 → 외부 노출 위험 |
| **Cloudflare Tunnel / Cloudflare for Teams** | 외부 라우팅, 저작권+비용 노출 |
| **ngrok / localtunnel** | "테스트 잠깐만"도 금지. 외부 URL 자체가 위험 |
| **public S3/Vercel/Streamlit Cloud 배포** | plan에 "외부 공개 X" 명시 |
| **DDNS + 포트 포워딩** | 가정용 ISP 환경에서 흔하지만 외부 노출. 절대 금지 |
| **nginx에 `allow all` / `auth_basic off`** | IP 필터 또는 인증 둘 중 하나라도 빠지면 외부 노출 |

---

## 점검 체크리스트 (배포 직후 + 월 1회)

- [ ] `netstat -an | grep 8501` — `127.0.0.1:8501` LISTEN만 있고 `0.0.0.0:8501` 없음
- [ ] 외부 IP에서 직접 접근 시도 → 차단됨 (방화벽/nginx allow/deny 또는 SSH 만 노출)
- [ ] `.env`가 git에 staged/tracked 아님 (`git status` + `git log -- .env`)
- [ ] nginx 사용 시: `curl -I http://lg-dash.internal` 결과에 `WWW-Authenticate: Basic` 헤더 존재
- [ ] htpasswd 파일 권한 `chmod 640` + owner `root:www-data`

---

## 참고

- Streamlit 공식 보안 가이드: <https://docs.streamlit.io/develop/concepts/configuration/options>
- nginx reverse proxy + WebSocket: <https://www.nginx.com/blog/websocket-nginx/>
- 운영: [RUNBOOK.md](RUNBOOK.md)
