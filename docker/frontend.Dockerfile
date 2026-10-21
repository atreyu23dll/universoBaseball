# Dos etapas: se compila con las dependencias de desarrollo y se sirve solo el
# resultado con el adaptador de Node.
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY --from=build /app/build ./build
EXPOSE 5173
CMD ["node", "build"]
