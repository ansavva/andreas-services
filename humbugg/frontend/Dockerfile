FROM public.ecr.aws/lambda/nodejs:24

WORKDIR ${LAMBDA_TASK_ROOT}

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY build ./build
COPY server ./server

CMD ["server/index.handler"]
