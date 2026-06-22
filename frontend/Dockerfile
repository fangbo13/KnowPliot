FROM node:20-slim

WORKDIR /app

COPY package.json ./

RUN npm config set registry https://registry.npmmirror.com && npm config set strict-ssl false && PUPPETEER_SKIP_DOWNLOAD=true npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
