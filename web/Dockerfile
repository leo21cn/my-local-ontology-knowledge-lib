FROM docker.m.daocloud.io/node:20-alpine AS build
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM docker.m.daocloud.io/nginx:alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8100
