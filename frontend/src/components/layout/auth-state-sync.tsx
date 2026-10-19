"use client";

import { useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { useAuthStore } from "@/store/auth-store";
import { useTenantStore } from "@/store/tenant-store";
import toast from "react-hot-toast";

export default function AuthStateSync({ children }: { children: React.ReactNode }) {
  const setSession = useAuthStore((state) => state.setSession);
  const setLoading = useAuthStore((state) => state.setLoading);
  const fetchTenantSettings = useTenantStore((state) => state.fetchTenantSettings);
  const router = useRouter();
  const pathname = usePathname();
  const redirectCheckId = useRef(0);

  useEffect(() => {
    const redirectAuthenticatedUser = async (session: Session | null) => {
      if (!session || !["/login", "/signup", "/"].includes(pathname)) {
        return;
      }

      const checkId = ++redirectCheckId.current;
      try {
        const hasTenant = await fetchTenantSettings();
        if (checkId === redirectCheckId.current) {
          router.replace(hasTenant ? "/dashboard" : "/onboarding");
        }
      } catch {
        if (checkId === redirectCheckId.current) {
          toast.error("Unable to verify your workspace. Please try again.");
        }
      }
    };

    const syncSession = async () => {
      setLoading(true);
      const { data: { session } } = await supabase.auth.getSession();
      setSession(session);
      setLoading(false);
      await redirectAuthenticatedUser(session);
    };
    
    void syncSession();

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setLoading(false);
      void redirectAuthenticatedUser(session);
    });

    return () => {
      redirectCheckId.current += 1;
      subscription.unsubscribe();
    };
  }, [setSession, setLoading, fetchTenantSettings, router, pathname]);

  return <>{children}</>;
}
