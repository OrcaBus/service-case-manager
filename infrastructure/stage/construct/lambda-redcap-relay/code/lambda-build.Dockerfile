FROM public.ecr.aws/lambda/nodejs:24-arm64 AS builder
WORKDIR /usr/app

COPY package.json ./
RUN npm install

COPY tsconfig.json index.ts ./
RUN npm run build
