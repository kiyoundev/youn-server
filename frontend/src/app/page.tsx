import { Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-semibold">youn-server dashboard</h1>
      <Button>
        <Rocket />
        shadcn + lucide check
      </Button>
    </main>
  );
}
