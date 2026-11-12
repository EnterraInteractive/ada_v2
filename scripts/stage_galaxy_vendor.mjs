import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, rename, rm, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const version = "1.73.3";
const expectedSha256 = "19b3be27040fc894e56d684d53c5f62526c25e5d27f37e8fe91fafff605e4ef4";
const source = `https://unpkg.com/3d-force-graph@${version}/dist/3d-force-graph.min.js`;
const target = resolve(root, "viewer/vendor/3d-force-graph.min.js");
const manifest = resolve(root, "viewer/vendor/VERSIONS.txt");

async function validExisting() {
  try {
    const info = await stat(target);
    const contents = await readFile(target, "utf8");
    const recorded = await readFile(manifest, "utf8");
    const expected = recorded.match(/SHA-256:\s*([a-f0-9]{64})/i)?.[1]?.toLowerCase();
    const actual = createHash("sha256").update(await readFile(target)).digest("hex");
    return info.size > 10000
      && contents.includes("ForceGraph3D")
      && recorded.includes(`3d-force-graph ${version}`)
      && Boolean(expected)
      && expected === expectedSha256
      && actual === expectedSha256;
  } catch {
    return false;
  }
}

if (!(await validExisting())) {
  await mkdir(dirname(target), { recursive: true });
  const response = await fetch(source, { redirect: "follow" });
  if (!response.ok) throw new Error(`Could not fetch pinned graph library: HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const text = bytes.toString("utf8");
  if (bytes.length < 10000 || !text.includes("ForceGraph3D")) {
    throw new Error("Downloaded graph library failed its content check.");
  }
  const temporary = target + ".tmp";
  await writeFile(temporary, bytes);
  await rm(target, { force: true });
  await rename(temporary, target);
}

const bytes = await readFile(target);
const sha256 = createHash("sha256").update(bytes).digest("hex");
await writeFile(manifest,
  `3d-force-graph ${version}\nSource: ${source}\nSHA-256: ${sha256}\nRuntime: local file; no CDN request\n`,
  "utf8");
console.log(`Knowledge Galaxy vendor staged: 3d-force-graph ${version} (${sha256})`);
