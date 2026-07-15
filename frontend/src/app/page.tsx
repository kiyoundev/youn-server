import { Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Bay } from "@/components/ui/bay";
import { StorageMeter } from "@/components/ui/storage-meter";
import StorageTile from "@/components/tiles/storage-tile";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      {/* <div className="flex gap-4">
        <Bay label="1" status="healthy" />
        <Bay label="2" status="warning" />
        <Bay label="3" status="error" />
        <Bay label="4" status="empty" />
      </div>
      <StorageMeter available={10} used={14} reserved={5} />
      <StorageTile /> */}
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Storage</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-7">
            <div className="flex gap-1">
              <Bay label="1" status="healthy" />
              {/* <Bay label="2" status="warning" /> */}
              {/* <Bay label="3" status="error" /> */}
              <Bay label="2" status="empty" />
            </div>
            <div className="flex flex-col gap-10">
              <Label className="text-[22px] font-normal">20.5TB</Label>
              <StorageMeter available={10} used={14} reserved={5} />
            </div>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
