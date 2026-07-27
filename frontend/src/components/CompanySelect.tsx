import { useEffect, useState } from 'react';
import { Button, Divider, Select } from 'antd';
import type { SelectProps } from 'antd';
import { CompanyItem, listCompanies } from '@/services/auth';

type Props = Omit<SelectProps<string | string[]>, 'options'> & {
  /** 传入 "multiple" 时开启多选 + 全选/清空 */
  mode?: 'multiple';
};

/** 公司下拉：支持单选和多选，多选时提供全选/清空快捷按钮。 */
export default function CompanySelect({ mode, onChange, value, ...rest }: Props) {
  const [options, setOptions] = useState<{ label: string; value: string }[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    listCompanies()
      .then((list: CompanyItem[]) =>
        setOptions(list.map((c) => ({ label: `${c.short_name}(${c.com_id})`, value: c.com_id }))),
      )
      .finally(() => setLoading(false));
  }, []);

  const allValues = options.map((o) => o.value);

  const handleSelectAll = () => {
    onChange?.(allValues as any, []);
  };
  const handleClearAll = () => {
    onChange?.([] as any, []);
  };

  return (
    <Select
      placeholder={mode === 'multiple' ? '请选择公司（支持多选/全选）' : '请选择公司'}
      showSearch
      optionFilterProp="label"
      loading={loading}
      options={options}
      mode={mode as any}
      value={value}
      onChange={onChange}
      maxTagCount={mode === 'multiple' ? 'responsive' : undefined}
      style={{ minWidth: mode === 'multiple' ? 280 : 200 }}
      dropdownRender={
        mode === 'multiple'
          ? (menu) => (
            <>
              <div style={{ padding: '4px 8px', display: 'flex', gap: 8 }}>
                <Button
                  type="link"
                  size="small"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={handleSelectAll}
                >
                  全选
                </Button>
                <Button
                  type="link"
                  size="small"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={handleClearAll}
                >
                  清空
                </Button>
              </div>
              <Divider style={{ margin: '0 0 4px 0' }} />
              {menu}
            </>
          )
          : undefined
      }
      {...rest}
    />
  );
}
