# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS build
WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmjs.org/
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=interview-guide-pnpm,target=/root/.local/share/pnpm/store \
    npm config set registry "$NPM_REGISTRY" \
    && npm install --global pnpm@10.26.2 \
    && pnpm config set store-dir /root/.local/share/pnpm/store \
    && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
