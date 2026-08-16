FROM node:20-alpine AS build
WORKDIR /app
COPY admin/package*.json ./
RUN npm install
COPY admin/ .
ARG VITE_API_KEY
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY admin/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
