import { NextResponse } from "next/server";

export async function GET() {
  const backend = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${backend}/health`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
