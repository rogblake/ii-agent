# PostgreSQL Integration & Authentication Guide

## Quick Start

### 1. Install Dependencies

```bash
bun add prisma@5.22.0 @prisma/client@5.22.0 bcrypt jose
bun add -d @types/bcrypt
```

### 2. Initialize Prisma

```bash
bunx prisma init --datasource-provider postgresql
```

---

## PostgreSQL Integration

### Schema Setup (`prisma/schema.prisma`)

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  password  String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

### Environment Variable (`.env`)

```env
DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require
JWT_SECRET=your-super-secret-key-change-in-production
```

### Prisma Client Singleton (`src/lib/prisma.ts`)

```typescript
import { PrismaClient } from "@prisma/client";

declare global {
  var prisma: PrismaClient | undefined;
}

export const prisma = global.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") global.prisma = prisma;
```

### Push Schema & Generate Client

```bash
bunx prisma db push
bunx prisma generate
```

---

## Authentication Implementation

### Auth Utilities (`src/lib/auth.ts`)

```typescript
import bcrypt from "bcrypt";
import { prisma } from "./prisma";

const SALT_ROUNDS = 10;

// Password hashing
export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, SALT_ROUNDS);
}

// Password verification
export async function verifyPassword(
  password: string,
  hashedPassword: string
): Promise<boolean> {
  return bcrypt.compare(password, hashedPassword);
}

// Create user with hashed password
export async function createUser(email: string, password: string, name?: string) {
  const hashedPassword = await hashPassword(password);
  return prisma.user.create({
    data: { email, password: hashedPassword, name: name || null },
    select: { id: true, email: true, name: true, createdAt: true },
  });
}

// Authenticate user
export async function authenticateUser(email: string, password: string) {
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) return null;

  const isValid = await verifyPassword(password, user.password);
  if (!isValid) return null;

  return { id: user.id, email: user.email, name: user.name, createdAt: user.createdAt };
}
```

### Session Management (`src/lib/session.ts`)

```typescript
import { cookies } from "next/headers";
import { SignJWT, jwtVerify } from "jose";

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || "default-secret-change-in-production"
);
const SESSION_COOKIE_NAME = "auth-session";

// Create JWT session
export async function createSession(user: { id: string; email: string; name: string | null }) {
  return new SignJWT({ userId: user.id, email: user.email, name: user.name })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(JWT_SECRET);
}

// Set session cookie
export async function setSessionCookie(token: string) {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/",
  });
}

// Get current session
export async function getSession() {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;
    if (!token) return null;

    const { payload } = await jwtVerify(token, JWT_SECRET);
    return {
      userId: payload.userId as string,
      email: payload.email as string,
      name: payload.name as string | null,
    };
  } catch {
    return null;
  }
}

// Clear session
export async function clearSession() {
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE_NAME);
}
```

---

## API Routes

### Register (`src/app/api/auth/register/route.ts`)

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createUser, findUserByEmail } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const { email, password, name } = await request.json();

  // Validation
  if (!email || !password) {
    return NextResponse.json({ error: "Email and password required" }, { status: 400 });
  }

  // Check existing user
  if (await findUserByEmail(email)) {
    return NextResponse.json({ error: "User already exists" }, { status: 409 });
  }

  // Create user
  const user = await createUser(email, password, name);
  return NextResponse.json(user, { status: 201 });
}
```

### Login (`src/app/api/auth/login/route.ts`)

```typescript
import { NextRequest, NextResponse } from "next/server";
import { authenticateUser } from "@/lib/auth";
import { createSession, setSessionCookie } from "@/lib/session";

export async function POST(request: NextRequest) {
  const { email, password } = await request.json();

  const user = await authenticateUser(email, password);
  if (!user) {
    return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
  }

  const token = await createSession(user);
  await setSessionCookie(token);

  return NextResponse.json({ user, message: "Login successful" });
}
```

### Logout (`src/app/api/auth/logout/route.ts`)

```typescript
import { NextResponse } from "next/server";
import { clearSession } from "@/lib/session";

export async function POST() {
  await clearSession();
  return NextResponse.json({ message: "Logged out successfully" });
}
```

### Session (`src/app/api/auth/session/route.ts`)

```typescript
import { NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ user: null, authenticated: false });
  }

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    select: { id: true, email: true, name: true, createdAt: true },
  });

  return NextResponse.json({ user, authenticated: !!user });
}
```

---

## Frontend Auth Context (`src/lib/auth-context.tsx`)

```typescript
"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string, name?: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch session on mount
  useEffect(() => {
    fetch("/api/auth/session")
      .then(res => res.json())
      .then(data => {
        if (data.authenticated) setUser(data.user);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (res.ok) setUser(data.user);
    return { success: res.ok, error: data.error };
  };

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

---

## File Structure

```
src/
├── app/
│   ├── api/auth/
│   │   ├── login/route.ts
│   │   ├── logout/route.ts
│   │   ├── register/route.ts
│   │   └── session/route.ts
│   ├── layout.tsx          # Wrap with AuthProvider
│   └── page.tsx
├── components/
│   ├── auth-form.tsx       # Login/Register UI
│   └── dashboard.tsx       # Logged-in view
└── lib/
    ├── auth.ts             # Auth utilities
    ├── auth-context.tsx    # React context
    ├── prisma.ts           # Prisma client
    └── session.ts          # JWT session handling
```

---

## Key Commands

```bash
# Install deps
bun add prisma@5.22.0 @prisma/client@5.22.0 bcrypt jose

# Push schema to DB
bunx prisma db push

# Generate client
bunx prisma generate

# Run tests
bun test

# Start dev server
bun run dev
```
