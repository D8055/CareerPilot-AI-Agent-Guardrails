import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { ConfirmProvider } from "@/components/Confirm";
import { ToastProvider } from "@/components/Toast";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <AppShell>{children}</AppShell>
      </ConfirmProvider>
    </ToastProvider>
  );
}
