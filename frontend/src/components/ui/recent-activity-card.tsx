"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { activityTypeLabel, type Activity } from "@/lib/mock-market";

interface RecentActivityCardProps {
  activity: Activity;
  logoColor: string;
}

function fmtAmount(value: number, currency: string) {
  return `$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function fmtDate(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

function fmtTime(date: string, time: string) {
  return new Date(`${date}T${time}:00`).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(/AM|PM/, (m) => m.toLowerCase());
}

const LIMIT_ORDER_SUBTYPES: Activity["activitySubType"][] = ["LIMIT_BUY", "STOP_LIMIT_BUY"];

function DetailRow({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="flex items-start justify-between py-1">
      <Label className="text-sm font-medium">{label}</Label>
      <div className="flex flex-col items-end gap-0.5 text-right">
        <Label className="text-sm">{value}</Label>
        {sub && <Label className="text-muted-foreground text-xs">{sub}</Label>}
      </div>
    </div>
  );
}

function RecentActivityCard({ activity, logoColor }: RecentActivityCardProps) {
  const [open, setOpen] = useState(false);

  const totalCost = fmtAmount(activity.netCashAmount, activity.currency);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-[12px] bg-muted/50">
      <CollapsibleTrigger className="flex w-full min-h-[68px] items-center gap-3 p-3 text-left">
        <div className="h-[30px] w-[30px] shrink-0 rounded" style={{ backgroundColor: logoColor }} />
        <div className="flex flex-1 flex-col justify-center gap-0.5">
          <Label className="text-[14px] font-normal">{activity.symbol}</Label>
          <div className="flex items-center gap-1.5">
            <Label className="text-muted-foreground text-[12px] font-normal">{activityTypeLabel(activity)}</Label>
            <Label className="text-muted-foreground text-[12px] font-normal">{activity.accountType}</Label>
          </div>
        </div>
        <Label className="whitespace-nowrap text-[14px] font-normal">{totalCost}</Label>
        <ChevronDown className={cn("size-4 shrink-0 opacity-50 transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-10 pb-3">
          <DetailRow label="Account" value={activity.accountType} />
          <DetailRow label="Status" value="Completed" />
          <DetailRow label="Submitted" value={fmtDate(activity.transactionDate)} sub={fmtTime(activity.transactionDate, activity.transactionTime)} />
          <DetailRow label="Filled" value={fmtDate(activity.settlementDate)} sub={fmtTime(activity.settlementDate, activity.settlementTime)} />
          <DetailRow label="Trading session" value="Market hours" sub="9:30 am–4:00 pm" />
          <Separator className="my-4" />
          <DetailRow label="Type" value={activityTypeLabel(activity)} />
          {LIMIT_ORDER_SUBTYPES.includes(activity.activitySubType) && (
            <DetailRow label="Limit price" value={fmtAmount(activity.unitPrice, activity.currency)} />
          )}
          <DetailRow label="Entered quantity" value={`${activity.quantity} shares`} />
          <DetailRow label="Filled quantity" value={`${activity.quantity} shares x ${fmtAmount(activity.unitPrice, activity.currency)}`} />
          {activity.fxRate !== null && <DetailRow label="Exchange rate" value={activity.fxRate.toFixed(6)} />}
          <Separator className="my-4" />
          <DetailRow label="Total cost" value={totalCost} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export { RecentActivityCard };
