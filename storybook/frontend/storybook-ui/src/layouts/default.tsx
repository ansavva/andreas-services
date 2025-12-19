import { Navbar } from "@/components/layout/navbar";

export default function DefaultLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex flex-col h-screen">
      <Navbar />
      <main className="container mx-auto max-w-7xl px-6 flex-grow pt-10">
        {children}
      </main>
      <footer className="w-full flex items-center justify-center py-3">
      </footer>
    </div>
  );
}
