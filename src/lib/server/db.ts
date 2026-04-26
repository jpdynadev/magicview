import { neon } from "@neondatabase/serverless";

import { serverEnv } from "@/lib/env";

type NeonSql = ReturnType<typeof neon>;

let sqlClient: NeonSql | undefined;

export function getSql() {
  sqlClient ??= neon(serverEnv.databaseUrl);
  return sqlClient;
}

export async function queryMany<T>(
  statement: string,
  params: unknown[] = [],
): Promise<T[]> {
  const sql = getSql();
  return (await sql.query(statement, params)) as T[];
}

export async function queryOne<T>(
  statement: string,
  params: unknown[] = [],
): Promise<T | null> {
  const rows = await queryMany<T>(statement, params);
  return rows[0] ?? null;
}

