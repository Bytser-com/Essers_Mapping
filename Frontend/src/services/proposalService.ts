import type { Proposal } from "../types/proposal";

const API_URL = import.meta.env.VITE_API_URL

export async function getProposal(company: string): Promise<Proposal> {
  const res = await fetch(`${API_URL}/proposals/${company}`);
  if (!res.ok) {
    throw new Error(`geen mapping gevonden (status ${res.status})`);
  }
  return res.json();
}