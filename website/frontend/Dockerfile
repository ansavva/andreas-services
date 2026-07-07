# React Router (framework mode) SSR handler on AWS Lambda.
# The private @ansavva/design-system is bundled into the server build at build
# time (see vite.config.ts ssr.noExternal), so this runtime install only needs
# public packages — no GitHub Packages token required in the image.
FROM public.ecr.aws/lambda/nodejs:20

WORKDIR ${LAMBDA_TASK_ROOT}

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY build ./build
COPY server ./server

# server/index.mjs exports `handler`.
CMD ["server/index.handler"]
