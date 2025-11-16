import { Link } from "@nextui-org/link";
import { Button } from "@nextui-org/react";

import DefaultLayout from "@/layouts/default";

export default function IndexPage() {
  return (
    <DefaultLayout>
      <section className="flex flex-col items-center justify-center gap-4 py-8 md:py-10">
        <div className="inline-block max-w-lg text-center justify-center">
          <h1 className="text-4xl font-extrabold leading-none">Be Anything</h1>
          <h1 className="text-4xl font-extrabold leading-none">You Want To Be</h1>
        </div>
        <Button
          href="/projects"
          as={Link}
          color="primary"
          className="rounded-full"
          variant="solid"
        >
          Get Started
        </Button>
      </section>
    </DefaultLayout>
  );
}
