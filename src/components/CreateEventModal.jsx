import { Dialog, Transition } from '@headlessui/react';
import PropTypes from 'prop-types';
import { Fragment, useEffect, useMemo, useState } from 'react';

function generateEventId(title, date) {
  const base = `${title}`
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
  const suffix = Math.random().toString(36).slice(2, 8);
  const normalizedBase = base || 'event';
  return `${normalizedBase}-${date.replace(/[^0-9]/g, '') || 'date'}-${suffix}`;
}

function CreateEventModal({ isOpen, onClose, onCreate }) {
  const [title, setTitle] = useState('');
  const [date, setDate] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setTitle('');
      setDate('');
      setDescription('');
      setError('');
    }
  }, [isOpen]);

  const isSubmitDisabled = useMemo(() => !title || !date || !description, [date, description, title]);

  const handleClose = () => {
    setError('');
    onClose();
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!title || !date || !description) {
      setError('All fields are required.');
      return;
    }

    onCreate({
      id: generateEventId(title, date),
      title: title.trim(),
      date,
      description: description.trim()
    });
  };

  return (
    <Transition show={isOpen} as={Fragment} appear>
      <Dialog onClose={handleClose} className="relative z-50">
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center px-4 py-12">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-xl rounded-3xl border border-slate-800/70 bg-slate-900/80 p-8 text-slate-100 shadow-2xl ring-1 ring-slate-800/70 backdrop-blur">
                <Dialog.Title className="text-2xl font-semibold text-slate-50">Create a new event</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-slate-400">
                  Fill in the details below to add an event to your timeline. You can refine it later when the
                  API is connected.
                </Dialog.Description>

                <form className="mt-8 flex flex-col gap-6" onSubmit={handleSubmit}>
                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Title
                    <input
                      type="text"
                      name="title"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                      placeholder="Enter a headline"
                      required
                    />
                  </label>

                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Date
                    <input
                      type="date"
                      name="date"
                      value={date}
                      onChange={(event) => setDate(event.target.value)}
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                      required
                    />
                  </label>

                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Description
                    <textarea
                      name="description"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      rows={4}
                      className="w-full resize-none rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                      placeholder="Describe what happened"
                      required
                    />
                  </label>

                  {error ? <p className="text-sm text-rose-400">{error}</p> : null}

                  <div className="flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      className="rounded-full border border-slate-700 px-5 py-2 text-sm font-semibold text-slate-300 transition hover:border-slate-600 hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmitDisabled}
                      className="inline-flex items-center justify-center rounded-full border border-sky-500/60 bg-sky-500/20 px-6 py-2 text-sm font-semibold text-sky-100 shadow-glow transition hover:border-sky-400 hover:bg-sky-500/30 hover:text-sky-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-800/80 disabled:text-slate-500"
                    >
                      Add event
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

CreateEventModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onCreate: PropTypes.func.isRequired
};

export default CreateEventModal;
