FROM node:20-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL
ARG VITE_MCP_SERVER_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL:-https://mcp.openmcpskills.click}
ENV VITE_MCP_SERVER_URL=${VITE_MCP_SERVER_URL:-https://mcp.openmcpskills.click/mcp}
COPY package*.json ./
RUN npm ci
COPY . .
RUN rm -f .env && npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
