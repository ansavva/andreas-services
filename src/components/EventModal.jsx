import { Dialog, Transition } from '@headlessui/react';
import PropTypes from 'prop-types';
import { Fragment, useEffect, useMemo, useState } from 'react';

function EventModal({ isOpen, mode, initialValues, isProcessing, error, onClose, onSubmit, onDelete }) {
  const [title, setTitle] = useState(initialValues.title);
  const [date, setDate] = useState(initialValues.date);
  const [description, setDescription] = useState(initialValues.description);
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setTitle(initialValues.title);
      setDate(initialValues.date);
      setDescription(initialValues.description);
      setLocalError('');
    }
  }, [initialValues, isOpen]);

  useEffect(() => {
    if (error) {
      setLocalError(error);
    }
  }, [error]);

  const isSubmitDisabled = useMemo(
    () => !title || !date || !description || isProcessing,
    [date, description, isProcessing, title]
  );

  const modalTitle = mode === 'edit' ? 'Edit event' : 'Create a new event';
  const submitLabel = mode === 'edit' ? 'Save changes' : 'Add event';

  const handleClose = () => {
    if (isProcessing) {
      return;
    }
    setLocalError('');
    onClose();
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!title || !date || !description) {
      setLocalError('All fields are required.');
      return;
    }

    onSubmit({
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
                <Dialog.Title className="text-2xl font-semibold text-slate-50">{modalTitle}</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-slate-400">
                  {mode === 'edit'
                    ? 'Update the timeline entry below. Changes will appear immediately on the timeline.'
                    : 'Fill in the details below to add an event to your timeline.'}
                </Dialog.Description>

                <form className="mt-8 flex flex-col gap-6" onSubmit={handleSubmit}>
                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Title
                    <input
                      type="text"
                      name="title"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60 disabled:opacity-50"
                      placeholder="Enter a headline"
                      required
                      disabled={isProcessing}
                    />
                  </label>

                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Date
                    <input
                      type="date"
                      name="date"
                      value={date}
                      onChange={(event) => setDate(event.target.value)}
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60 disabled:opacity-50"
                      required
                      disabled={isProcessing}
                    />
                  </label>

                  <label className="flex flex-col gap-2 text-sm font-medium text-slate-200">
                    Description
                    <textarea
                      name="description"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      rows={4}
                      className="w-full resize-none rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60 disabled:opacity-50"
                      placeholder="Describe what happened"
                      required
                      disabled={isProcessing}
                    />
                  </label>

                  {localError ? <p className="text-sm text-rose-400">{localError}</p> : null}

                  <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end sm:gap-4">
                    <button
                      type="button"
                      onClick={handleClose}
                      className="rounded-full border border-slate-700 px-5 py-2 text-sm font-semibold text-slate-300 transition hover:border-slate-600 hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={isProcessing}
                    >
                      Cancel
                    </button>
                    {onDelete ? (
                      <button
                        type="button"
                        onClick={onDelete}
                        className="rounded-full border border-rose-500/60 bg-rose-500/20 px-5 py-2 text-sm font-semibold text-rose-100 shadow-glow transition hover:border-rose-400 hover:bg-rose-500/30 hover:text-rose-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isProcessing}
                      >
                        Delete event
                      </button>
                    ) : null}
                    <button
                      type="submit"
                      disabled={isSubmitDisabled}
                      className="inline-flex items-center justify-center rounded-full border border-sky-500/60 bg-sky-500/20 px-6 py-2 text-sm font-semibold text-sky-100 shadow-glow transition hover:border-sky-400 hover:bg-sky-500/30 hover:text-sky-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-800/80 disabled:text-slate-500"
                    >
                      {isProcessing ? 'Saving…' : submitLabel}
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

EventModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  mode: PropTypes.oneOf(['create', 'edit']).isRequired,
  initialValues: PropTypes.shape({
    title: PropTypes.string,
    date: PropTypes.string,
    description: PropTypes.string
  }).isRequired,
  isProcessing: PropTypes.bool,
  error: PropTypes.string,
  onClose: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired,
  onDelete: PropTypes.func
};

EventModal.defaultProps = {
  isProcessing: false,
  error: '',
  onDelete: undefined
};

export default EventModal;
