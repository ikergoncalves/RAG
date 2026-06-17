# syntax=docker/dockerfile:1

# --- Build stage: compile the Vite app to static assets ---------------------
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first so this layer is cached unless the lockfile
# changes. `npm ci` installs the exact locked versions for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Runtime stage: serve static assets via nginx (also proxies the API) ----
# The nginx-unprivileged image runs as a non-root user (uid 101) and its server
# block listens on 8080, so binding a privileged (<1024) port is never needed.
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Our server block listens on 8080 to match the unprivileged base image.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
