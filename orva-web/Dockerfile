FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Default to empty (relative URLs) so fetches go through whatever origin the
# user is on -- in production that's https://orvauae.com and nginx proxies
# /api/* to the FastAPI container. No mixed-content blocking, no CORS
# preflight. Set NEXT_PUBLIC_API_URL via docker-compose `args:` if you
# need a different base in dev.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
