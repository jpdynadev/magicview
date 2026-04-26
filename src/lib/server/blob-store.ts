import { getStore } from "@netlify/blobs";

function store() {
  const siteID = process.env.SITE_ID ?? process.env.NETLIFY_SITE_ID;
  const token = process.env.NETLIFY_AUTH_TOKEN ?? process.env.NETLIFY_API_TOKEN;

  // Some Netlify sites don’t currently inject `NETLIFY_BLOBS_CONTEXT` into the
  // Functions runtime. In that case, pass `siteID` + `token` explicitly.
  if (siteID && token) {
    return getStore("magicview", { siteID, token });
  }

  return getStore("magicview");
}

export async function blobGetJson<T>(key: string): Promise<T | null> {
  const value = await store().get(key, { type: "json" }).catch(() => null);
  return (value as T | null) ?? null;
}

export async function blobSetJson(key: string, value: unknown) {
  await store().setJSON(key, value);
}

export async function blobDelete(key: string) {
  await store().delete(key);
}

export async function blobListKeys(prefix: string): Promise<string[]> {
  const keys: string[] = [];
  const iterable = store().list({ prefix, paginate: true });
  for await (const page of iterable) {
    keys.push(...page.blobs.map((blob) => blob.key));
  }

  return keys;
}
