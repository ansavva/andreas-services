import { Popover, Transition } from '@headlessui/react';
import { useDatePicker } from '@rehookify/datepicker';
import PropTypes from 'prop-types';
import { Fragment, useMemo } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faChevronRight, faCalendarDay } from '@fortawesome/free-solid-svg-icons';

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function getDisplayLabel(date) {
  if (!date) {
    return 'Select date';
  }

  const formatted = new Date(date);
  if (Number.isNaN(formatted.getTime())) {
    return 'Select date';
  }

  return formatted.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

function DatePickerField({ value, onChange, disabled, label, buttonClassName, align }) {
  const selectedDate = useMemo(() => {
    if (!value) {
      return [];
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return [];
    }
    return [parsed];
  }, [value]);

  const {
    data: { calendars },
    propGetters: { dayButton, nextMonthButton, prevMonthButton }
  } = useDatePicker({
    selectedDates: selectedDate,
    onDatesChange: (dates) => {
      const next = dates?.[0];
      onChange(next ? next.toISOString().slice(0, 10) : '');
    },
    dates: { mode: 'single' },
    calendar: { startDay: 0 },
    locale: { weekStartsOn: 0 }
  });

  const calendar = calendars?.[0];
  const monthName = calendar?.monthName ?? calendar?.month;
  const monthLabel = calendar ? `${monthName} ${calendar.year}` : '';
  const days = calendar?.weeks?.flat?.() ?? calendar?.days ?? [];

  return (
    <div className="flex flex-col gap-2">
      {label ? <span className="text-sm font-medium text-slate-200">{label}</span> : null}
      <Popover className="relative">
        <Popover.Button
          disabled={disabled}
          className={`inline-flex w-full items-center justify-between rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-left text-base text-slate-100 transition hover:border-sky-500/50 hover:text-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-500 ${
            buttonClassName || ''
          }`}
        >
          <span className="truncate">{getDisplayLabel(value)}</span>
          <span className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-500">
            <FontAwesomeIcon icon={faCalendarDay} />
            Date
          </span>
        </Popover.Button>

        <Transition
          as={Fragment}
          enter="transition ease-out duration-150"
          enterFrom="opacity-0 scale-95"
          enterTo="opacity-100 scale-100"
          leave="transition ease-in duration-120"
          leaveFrom="opacity-100 scale-100"
          leaveTo="opacity-0 scale-95"
        >
          <Popover.Panel
            className={`absolute z-10 mt-3 w-[320px] rounded-3xl border border-slate-800/80 bg-slate-900/90 p-4 shadow-2xl ring-1 ring-slate-800/80 backdrop-blur ${
              align === 'right' ? 'right-0' : 'left-0'
            }`}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm font-semibold text-slate-100">{monthLabel}</div>
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <button
                  type="button"
                  className="rounded-full border border-slate-700 px-3 py-1 transition hover:border-slate-600 hover:text-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                  {...prevMonthButton({ disabled })}
                >
                  <FontAwesomeIcon icon={faChevronLeft} />
                </button>
                <button
                  type="button"
                  className="rounded-full border border-slate-700 px-3 py-1 transition hover:border-slate-600 hover:text-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                  {...nextMonthButton({ disabled })}
                >
                  <FontAwesomeIcon icon={faChevronRight} />
                </button>
              </div>
            </div>
            <div className="grid grid-cols-7 gap-1 text-center text-xs uppercase tracking-wide text-slate-400">
              {WEEKDAY_LABELS.map((weekday) => (
                <span key={weekday} className="py-1">
                  {weekday}
                </span>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-7 gap-1 text-sm">
              {days.map((day) => {
                const isSelected = day?.selected;
                const isToday = day?.today;
                const isOutside = day && calendar && day.month !== calendar.month;

                return (
                  <button
                    key={day?.$date?.toString?.() ?? day?.id}
                    type="button"
                    className={`h-10 rounded-xl border px-2 py-1 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${
                      isSelected
                        ? 'border-sky-400 bg-sky-500/20 text-sky-100'
                        : 'border-slate-800 bg-slate-900/70 text-slate-200 hover:border-slate-600 hover:bg-slate-800'
                    } ${isOutside ? 'opacity-50' : ''} ${isToday ? 'ring-1 ring-slate-500/60' : ''}`}
                    {...dayButton(day, { disabled })}
                  >
                    {day?.day ?? day?.label ?? day?.date?.getDate?.() ?? ''}
                  </button>
                );
              })}
            </div>
          </Popover.Panel>
        </Transition>
      </Popover>
    </div>
  );
}

DatePickerField.propTypes = {
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  label: PropTypes.string,
  buttonClassName: PropTypes.string,
  align: PropTypes.oneOf(['left', 'right'])
};

DatePickerField.defaultProps = {
  value: '',
  disabled: false,
  label: undefined,
  buttonClassName: '',
  align: 'left'
};

export default DatePickerField;
