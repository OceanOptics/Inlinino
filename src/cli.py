# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-16 17:17:09
# @Last Modified by:   nils
# @Last Modified time: 2016-07-27 17:04:09

import cmd
import os


class CLI(cmd.Cmd):
    '''
    Command Line Interface
    '''

    # Configuring Cmd Through Attributes
    prompt = '>>'
    intro = 'Inlinino 2.0 alpha (May 16, 2016)\n' + \
            'Type "help", "support", or "credits" for more information.'

    doc_header = 'List of commands available (type help <topic>):'
    # misc_header = 'misc_header'
    # undoc_header = 'undoc_header'
    # ruler = '-'

    # Initialize interface
    def __init__(self, _app):
        cmd.Cmd.__init__(self)
        self.m_app = _app

    # Instruments
    def do_instrument(self, line):
        if line == "":
            print('WARNING: Command instrument take an argument ' +
                  '(connect, close, or list).')
            return

        arg = line.split()
        narg = len(arg)

        if arg[0] == "connect":
            if narg != 2 and narg != 3:
                print('WARNING: ' + arg[0] + ' takes 1 or 2 arguments\n' +
                      '\t specify instrument to connect and the port (option)')
                return
            # Connect to instrument specified in arg[1]
            if arg[1] not in self.m_app.m_instruments.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('Unknown instrument')
                return
            if narg == 2:
                if not self.m_app.m_instruments[arg[1]].Connect():
                    print('ERROR: Instrument not connected.')
            else:
                if not self.m_app.m_instruments[arg[1]].Connect(arg[2]):
                    print('ERROR: Instrument not connected.')
        elif arg[0] == "close":
            if narg != 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument\n' +
                      '\t specify instrument to disconnect')
                return
            # Connect to instrument specified in arg[1]
            if arg[1] not in self.m_app.m_instruments.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('Unknown instrument')
                return
            self.m_app.m_instruments[arg[1]].Close()
        elif arg[0] == 'list':
            if narg > 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument maximum\n' +
                      '\t list or list ports')
                return
            if narg < 2:
                # Display list of instruments
                foo = ''
                for instr_key in self.m_app.m_instruments.keys():
                    foo += str(instr_key) + '\n'
                print(foo, end='', flush=True)
            elif arg[1] == 'ports':
                # Display list of ports
                self.m_app.m_com.ListPorts()
                print(self.m_app.m_com)
            else:
                print('WARNING: Unknown argument ' + arg[1] + ' for list')
        elif arg[0] == 'read':
            # Read Cache from instruments
            if narg > 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument maximum\n' +
                      '\t read or read [instrument_name]')
                return
            elif narg == 1:
                for inst, inst in self.m_app.m_instruments.items():
                    print(inst.ReadCache())
            elif narg == 2:
                if arg[1] not in self.m_app.m_instruments.keys():
                    if self.m_app.m_cfg.m_v > 0:
                        print('Unknown instrument')
                    return
                print(self.m_app.m_instruments[arg[1]].ReadCache())
        else:
            print('WARNING: Unknown command ' + line)

    def complete_instrument(self, text, line, begidx, endidx):
        cmd_available = ['connect', 'close', 'list', 'read']
        if not text:
            completions = cmd_available
        else:
            completions = [f for f in cmd_available
                           if f.startswith(text)]
        return completions

    def help_instrument(self):
        print('instrument [arg]\n\t' +
              '<connect> [instrument_name] [port_name]\n\t' +
              '\tconnect to instrument using specified port\n\t' +
              '<close> [instrument_name]\n\t' +
              '\tclose connection with instrument\n\t' +
              '<list> [ports]\n\t' +
              '\tlist all instruments or ports\n\t'
              '<read> [instrument_name]\n\t' +
              '\tread instrument cache\n\t' +
              '\tif [instrument_name] is not specified,\n\t' +
              '\t\tread cache of all instruments')

    # Log
    def do_log(self, line):
        arg = line.split()
        narg = len(arg)
        if narg == 0 or narg > 2:
            print('WARNING: Command log take 1 or 2 arguments ' +
                  '(start, stop or header).')
        elif arg[0] == "start":
            self.m_app.m_log_data.Start()
            print("Start logging data.")
        elif arg[0] == "stop":
            self.m_app.m_log_data.Stop()
            print("Stop logging data.")
        elif arg[0] == "header":
            if narg != 2:
                print('WARNING: ' + arg[0] + ' takes 1 argument\n' +
                      '\t header [log_file_name_header]')
                return
            self.m_app.m_log_data.m_file_header = arg[1]
        elif arg[0] == "filename":
            if (self.m_app.m_log_data.m_file_name is not None and
                    self.m_app.m_log_data.m_active_log):
                foo = os.path.join(self.m_app.m_log_data.m_file_path,
                                   self.m_app.m_log_data.m_file_name)
            else:
                foo = os.path.join(self.m_app.m_log_data.m_file_path,
                                   self.m_app.m_log_data.m_file_header) \
                    + '_yyyymmdd_HHMMSS.csv'
            print(foo)
        else:
            print('WARNING: Unknown command ' + line)

    def complete_log(self, text, line, begidx, endidx):
        cmd_available = ['start', 'stop', 'header', 'filename']
        if not text:
            completions = cmd_available
        else:
            completions = [f for f in cmd_available
                           if f.startswith(text)]
        return completions

    def help_log(self):
        print('log [arg]\n\t<start> logging data\n\t<stop> logging data\n\t' +
              '<header> [log_file_name_header] change file name header' +
              '\n\t<filename> return current filename')

    # Status
    def do_status(self, line):
        print(self.m_app)

    def help_status(self):
        print('status\n\tDisplay some parameters and state of instruments')

    # Plot (Use matplotlib)
    # def do_plot(self, line):
    #     arg = line.split()
    #     narg = len(arg)
    #     if narg == 0 or narg > 2:
    #         print('WARNING: Command plot take 1 argument ' +
    #               '(start or stop).')
    #     elif arg[0] == "start":
    #         self.m_app.m_plot.Start()
    #     elif arg[0] == "stop":
    #         self.m_app.m_plot.Stop()
    #     elif arg[0] == "header":
    #         if narg != 2:
    #             print('WARNING: ' + arg[0] + ' takes 1 argument\n' +
    #                   '\t header [log_file_name_header]')
    #             return
    #         self.m_app.m_log_data.m_file_header = arg[1]
    #     else:
    #         print('WARNING: Unknown command ' + line)

    # def complete_plot(self, text, line, begidx, endidx):
    #     cmd_available = ['start', 'stop']
    #     if not text:
    #         completions = cmd_available
    #     else:
    #         completions = [f for f in cmd_available
    #                        if f.startswith(text)]
    #     return completions

    # def help_plot(self):
    #     print('log [arg]\n\t<start> plotting data\n\t<stop> plotting data' +
    #           '\n\tThis function has not been tested yet.' +
    #           '\n\tBased on matplotlib')

    # Exit
    def do_exit(self, line):
        return self.do_EOF(line)

    def help_exit(self):
        return self.help_EOF()

    def do_EOF(self, line):
        return True

    def help_EOF(self):
        print('exit or EOF\n\t' +
              'Quit Inlinino after:\n\t' +
              '\t- closing all instrument connection\n\t' +
              '\t- stoping all logging activity\n\t' +
              'All data is saved automatically.')

    # Credits
    def do_credits(self, line):
        print('### Credits ###\n' +
              'Developped by Nils Haëntjens (University of Maine)\n' +
              'Inspired by Instrumentino from Joel Koenka\n')

    def help_credits(self):
        print('credits\n\t' +
              'Display credits\n\t')

    # Support
    def do_support(self, line):
        print('### Support ###\n' +
              'Send questions, bug reports, fixes, enhancements, t-shirts, ' +
              'money, lobsters & beers to Nils\n' +
              '<nils.haentjens+inlinino@maine.edu>')

    def help_support(self):
        print('support\n\t' +
              'Display support informations\n\t')

    # Override Cmd class methods
    def emptyline(self):
        # By default empty line re-do previous command
        # Rewrite it to do nothing
        pass

    def do_shell(self, line):
        # Run a shell command
        print(os.popen(line).read())

    def help_shell(self):
        print('! or shell\n\tRun command on host shell')


if __name__ == '__main__':
    CLI(None).cmdloop()
