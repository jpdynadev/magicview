import { compare, hash } from "bcryptjs";
import { jwtVerify, SignJWT } from "jose";

import { serverEnv } from "@/lib/env";
import type { AppUser } from "@/lib/types";

function getSecret() {
  return new TextEncoder().encode(serverEnv.jwtSecret);
}

interface AuthJwtPayload {
  sub: string;
  email: string;
}

export async function hashPassword(password: string): Promise<string> {
  return hash(password, 12);
}

export async function verifyPassword(
  password: string,
  passwordHash: string,
): Promise<boolean> {
  return compare(password, passwordHash);
}

export async function signUserToken(user: AppUser): Promise<string> {
  return new SignJWT({ email: user.email })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(user.id)
    .setIssuedAt()
    .setExpirationTime("14d")
    .sign(getSecret());
}

export async function verifyUserToken(token: string): Promise<AuthJwtPayload> {
  const { payload } = await jwtVerify(token, getSecret());

  if (!payload.sub || typeof payload.email !== "string") {
    throw new Error("Invalid auth token.");
  }

  return {
    sub: payload.sub,
    email: payload.email,
  };
}
