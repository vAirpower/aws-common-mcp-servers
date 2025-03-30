# Use an official Node.js runtime as a parent image
# Using Alpine Linux for a smaller image size
FROM node:18-alpine AS builder

WORKDIR /usr/src/app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies needed for build
RUN npm ci

# Copy the rest of the application source code
COPY . .

# Build the TypeScript code
RUN npm run build

# --- Production Stage ---
FROM node:18-alpine

WORKDIR /usr/src/app

# Copy package files again for production dependencies
COPY package.json package-lock.json* ./

# Install only production dependencies
RUN npm ci --only=production

# Copy the built application from the builder stage
COPY --from=builder /usr/src/app/build ./build

# Create a non-root user and group
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Change ownership of the application directory
RUN chown -R appuser:appgroup /usr/src/app

# Switch to the non-root user
USER appuser

# The command to run the application (MCP servers typically run via stdio)
CMD [ "node", "build/index.js" ]