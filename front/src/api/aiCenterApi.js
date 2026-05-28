import { fetchJson } from "./client";

export async function listImportedSkills() {
  return fetchJson("/api/v1/ai-center/skills", { timeout: 20000 });
}

export async function importGithubSkill(payload) {
  return fetchJson("/api/v1/ai-center/skills/import-github", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 30000,
  });
}

export async function enableSkill(id) {
  return fetchJson(`/api/v1/ai-center/skills/${id}/enable`, {
    method: "POST",
    body: JSON.stringify({}),
    timeout: 20000,
  });
}

export async function disableSkill(id) {
  return fetchJson(`/api/v1/ai-center/skills/${id}/disable`, {
    method: "POST",
    body: JSON.stringify({}),
    timeout: 20000,
  });
}

export async function deleteSkill(id) {
  return fetchJson(`/api/v1/ai-center/skills/${id}`, {
    method: "DELETE",
    timeout: 20000,
  });
}
