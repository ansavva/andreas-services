"use client"

import Image from "next/image";
import { 
  Card, 
  CardBody, 
  Button, 
  Link, 
  Spacer,
  Code,
  Divider
} from "@heroui/react";
import { 
  DocumentTextIcon, 
  WindowIcon, 
  GlobeAltIcon 
} from "@heroicons/react/24/outline";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-8">
      {/* Main Content */}
      <main className="flex flex-col items-center gap-8 max-w-2xl w-full">
        {/* Logo */}
        <div className="flex justify-center">
          <Image
            className="dark:invert"
            src="/next.svg"
            alt="Next.js logo"
            width={180}
            height={38}
            priority
          />
        </div>

        {/* Welcome Card */}
        <Card className="w-full">
          <CardBody className="p-6">
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-center sm:text-left">
                Get Started with HeroUI
              </h2>
              <div className="space-y-3 text-sm">
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-xs font-semibold">
                    1
                  </span>
                  <div>
                    Get started by editing{" "}
                    <Code size="sm" className="font-semibold">
                      src/app/page.tsx
                    </Code>
                    .
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-xs font-semibold">
                    2
                  </span>
                  <div>Save and see your changes instantly.</div>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Action Buttons */}
        <div className="flex gap-4 items-center flex-col sm:flex-row w-full">
          <Button
            as={Link}
            href="https://heroui.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            color="primary"
            size="lg"
            className="w-full sm:w-auto"
          >
            Explore HeroUI
          </Button>
          <Button
            as={Link}
            href="https://nextjs.org/docs"
            target="_blank"
            rel="noopener noreferrer"
            variant="bordered"
            size="lg"
            className="w-full sm:w-auto"
          >
            Next.js Docs
          </Button>
        </div>
      </main>

      <Spacer y={4} />

      {/* Footer */}
      <footer className="w-full max-w-2xl">
        <Divider className="mb-6" />
        <div className="flex gap-6 flex-wrap items-center justify-center">
          <Link
            href="https://heroui.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm"
            showAnchorIcon
          >
            <DocumentTextIcon className="w-4 h-4" />
            Learn HeroUI
          </Link>
          <Link
            href="https://heroui.com/examples"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm"
            showAnchorIcon
          >
            <WindowIcon className="w-4 h-4" />
            Examples
          </Link>
          <Link
            href="https://nextjs.org"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm"
            showAnchorIcon
          >
            <GlobeAltIcon className="w-4 h-4" />
            Next.js
          </Link>
        </div>
      </footer>
    </div>
  );
}
