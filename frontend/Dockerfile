# Railway web 이미지 (infra/railway_setup.md). 빌드 컨텍스트 = frontend/ (Root Directory /frontend)
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
# VITE_ 값은 빌드 결과에 그대로 들어간다. 비밀값을 넣지 않는다(src/api/config.ts).
# 기본값이 mock이라 여기서 http로 고정한다. Railway 서비스 변수로 같은 이름을 넣으면 그 값이 쓰인다
ARG VITE_API_MODE=http
ARG VITE_USER_ID=1
RUN npm run build

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
